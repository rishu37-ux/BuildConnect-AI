"""robots.txt compliance and per-domain rate limiting."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx


class DomainRateLimiter:
    """Ensures at least `min_delay` seconds between requests to the same host."""

    def __init__(self, min_delay: float):
        self.min_delay = min_delay
        self._next_slot: dict[str, float] = {}
        self._crawl_delay: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def set_crawl_delay(self, host: str, delay: float | None) -> None:
        if delay:
            self._crawl_delay[host] = float(delay)

    def penalize(self, host: str, seconds: float) -> None:
        """Push the host's next slot back, e.g. after a 429 or Retry-After."""
        self._next_slot[host] = max(self._next_slot.get(host, 0.0), time.monotonic() + seconds)

    async def wait(self, host: str) -> None:
        async with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot.get(host, 0.0))
            delay = max(self.min_delay, self._crawl_delay.get(host, 0.0))
            self._next_slot[host] = slot + delay
        if slot > now:
            await asyncio.sleep(slot - now)


class RobotsCache:
    def __init__(self, client: httpx.AsyncClient, user_agent: str, enabled: bool = True):
        self._client = client
        self._ua = user_agent
        self._enabled = enabled
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def _parser_for(self, origin: str) -> RobotFileParser | None:
        lock = self._locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin not in self._parsers:
                parser: RobotFileParser | None = RobotFileParser()
                try:
                    resp = await self._client.get(f"{origin}/robots.txt", headers={"User-Agent": self._ua})
                    if resp.status_code in (401, 403):
                        parser.disallow_all = True
                    elif resp.status_code >= 400:
                        parser = None  # no robots.txt -> everything allowed
                    else:
                        parser.parse(resp.text.splitlines())
                except httpx.HTTPError:
                    parser = None
                self._parsers[origin] = parser
            return self._parsers[origin]

    async def allowed(self, url: str) -> bool:
        if not self._enabled:
            return True
        parts = urlsplit(url)
        parser = await self._parser_for(f"{parts.scheme}://{parts.netloc}")
        return parser is None or parser.can_fetch(self._ua, url)

    async def crawl_delay(self, url: str) -> float | None:
        parts = urlsplit(url)
        parser = await self._parser_for(f"{parts.scheme}://{parts.netloc}")
        return parser.crawl_delay(self._ua) if parser else None
