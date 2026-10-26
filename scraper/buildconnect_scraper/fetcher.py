"""HTTP fetching with proxy rotation, retries and challenge detection.

Proxy rotation exists for *reliability* (flaky egress, regional routing,
spreading load). It is deliberately not used to get around a site's access
controls: when a site serves a CAPTCHA / bot challenge or a hard block, the
fetcher raises `AccessChallenge` and the agent stops crawling that domain.
Sites that challenge automated clients should be accessed through an official
API, a data-sharing agreement, or manual review instead.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from .config import Settings
from .politeness import DomainRateLimiter, RobotsCache
from .proxy import ProxyPool, ProxyState

log = logging.getLogger(__name__)

# Markers that only appear on interstitial challenge / block pages.
_INTERSTITIAL_MARKERS = re.compile(
    r"/cdn-cgi/challenge-platform|cf_chl_|challenges\.cloudflare\.com"
    r"|verify (that )?you are (a )?human|are you a robot|unusual traffic from your computer",
    re.I,
)
# CAPTCHA widgets. Many legitimate pages embed these in a contact form, so they
# only count as a challenge when the page is an error or has almost no content.
_WIDGET_MARKERS = re.compile(r"g-recaptcha|grecaptcha|h-captcha|hcaptcha\.com|cf-turnstile", re.I)
_TAGS = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.S | re.I)
_RETRYABLE_STATUS = {500, 502, 503, 504}


class FetchError(Exception):
    pass


class DisallowedByRobots(FetchError):
    pass


class AccessChallenge(FetchError):
    """The site presented a CAPTCHA, bot challenge or access block."""

    def __init__(self, url: str, reason: str):
        super().__init__(f"{reason} at {url}")
        self.url = url
        self.reason = reason


@dataclass
class Page:
    url: str
    status: int
    html: str
    proxy: str


def detect_challenge(resp: httpx.Response) -> str | None:
    """Return a reason string if the response is a CAPTCHA/bot wall, else None."""
    if resp.headers.get("cf-mitigated") == "challenge":
        return "cloudflare challenge"
    ctype = resp.headers.get("content-type", "")
    if "html" in ctype or not ctype:
        head = resp.text[:50_000]
        if _INTERSTITIAL_MARKERS.search(head):
            return "bot challenge page"
        if _WIDGET_MARKERS.search(head):
            visible = " ".join(_TAGS.sub(" ", head).split())
            if resp.status_code >= 400 or len(visible) < 500:
                return "captcha wall"
    if resp.status_code in (401, 403, 451):
        return f"access denied (HTTP {resp.status_code})"
    return None


ClientFactory = Callable[[str | None], httpx.AsyncClient]


class Fetcher:
    def __init__(self, settings: Settings, client_factory: ClientFactory | None = None):
        self.settings = settings
        self.proxies = ProxyPool(settings.proxies)
        self.rate_limiter = DomainRateLimiter(settings.min_delay)
        self._factory = client_factory or self._default_client
        self._clients: dict[str | None, httpx.AsyncClient] = {}
        self.robots = RobotsCache(self._client(None), settings.user_agent, settings.respect_robots)
        self._robots_delay_applied: set[str] = set()

    def _default_client(self, proxy: str | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            proxy=proxy,
            timeout=self.settings.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                "Accept-Language": "en-IN,en;q=0.9,hi;q=0.6,pa;q=0.5",
            },
        )

    def _client(self, proxy: str | None) -> httpx.AsyncClient:
        if proxy not in self._clients:
            self._clients[proxy] = self._factory(proxy)
        return self._clients[proxy]

    async def aclose(self) -> None:
        await asyncio.gather(*(c.aclose() for c in self._clients.values()))

    async def fetch(self, url: str) -> Page:
        host = urlsplit(url).netloc
        if not await self.robots.allowed(url):
            raise DisallowedByRobots(f"robots.txt disallows {url}")
        if host not in self._robots_delay_applied:
            self.rate_limiter.set_crawl_delay(host, await self.robots.crawl_delay(url))
            self._robots_delay_applied.add(host)

        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            await self.rate_limiter.wait(host)
            proxy: ProxyState = self.proxies.acquire()
            try:
                resp = await self._client(proxy.url).get(url)
            except httpx.TransportError as exc:  # connect/read/proxy errors -> rotate
                self.proxies.report_failure(proxy)
                last_error = exc
                log.debug("transport error via %s on %s: %s", proxy.label, url, exc)
                await self._backoff(attempt)
                continue

            if resp.status_code == 429:
                # Rate limited: honour Retry-After for the whole host, keep the proxy healthy.
                retry_after = _retry_after_seconds(resp, default=30.0 * attempt)
                self.rate_limiter.penalize(host, retry_after)
                last_error = FetchError(f"HTTP 429 from {host}")
                continue

            reason = detect_challenge(resp)
            if reason:
                raise AccessChallenge(url, reason)

            if resp.status_code in _RETRYABLE_STATUS:
                self.proxies.report_failure(proxy)
                last_error = FetchError(f"HTTP {resp.status_code} from {url}")
                await self._backoff(attempt)
                continue

            self.proxies.report_success(proxy)
            if resp.status_code >= 400:
                raise FetchError(f"HTTP {resp.status_code} from {url}")
            if "html" not in resp.headers.get("content-type", "text/html"):
                raise FetchError(f"non-HTML content at {url}")
            return Page(url=str(resp.url), status=resp.status_code, html=resp.text, proxy=proxy.label)

        raise FetchError(f"giving up on {url} after {self.settings.max_retries} attempts: {last_error}")

    @staticmethod
    async def _backoff(attempt: int) -> None:
        await asyncio.sleep(min(2 ** attempt, 30) * random.uniform(0.5, 1.0))


def _retry_after_seconds(resp: httpx.Response, default: float) -> float:
    try:
        return max(1.0, min(float(resp.headers["retry-after"]), 3600.0))
    except (KeyError, ValueError):
        return default
