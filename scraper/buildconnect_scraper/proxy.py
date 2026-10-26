"""Health-aware proxy rotation.

Proxies are picked round-robin among those that are not cooling down. Each
failure doubles a proxy's cooldown (capped), each success resets it, so a
bad egress gets sidelined automatically without being dropped forever.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

DIRECT = None  # sentinel meaning "no proxy"


@dataclass
class ProxyState:
    url: str | None
    failures: int = 0
    successes: int = 0
    cooldown_until: float = 0.0

    @property
    def label(self) -> str:
        if self.url is None:
            return "direct"
        # host:port only, so credentials never reach logs or run stats.
        parts = urlsplit(self.url)
        return f"{parts.hostname}:{parts.port}" if parts.port else str(parts.hostname)


class ProxyPool:
    def __init__(self, proxies: list[str], base_cooldown: float = 30.0, max_cooldown: float = 900.0,
                 clock=time.monotonic):
        urls: list[str | None] = list(dict.fromkeys(proxies)) or [DIRECT]
        self._states = [ProxyState(u) for u in urls]
        self._cycle = itertools.cycle(range(len(self._states)))
        self._base = base_cooldown
        self._max = max_cooldown
        self._clock = clock

    def __len__(self) -> int:
        return len(self._states)

    def acquire(self) -> ProxyState:
        """Next healthy proxy; if all are cooling down, the one that recovers soonest."""
        now = self._clock()
        for _ in range(len(self._states)):
            state = self._states[next(self._cycle)]
            if state.cooldown_until <= now:
                return state
        return min(self._states, key=lambda s: s.cooldown_until)

    def report_success(self, state: ProxyState) -> None:
        state.successes += 1
        state.failures = 0
        state.cooldown_until = 0.0

    def report_failure(self, state: ProxyState) -> None:
        state.failures += 1
        delay = min(self._base * 2 ** (state.failures - 1), self._max)
        state.cooldown_until = self._clock() + delay

    def snapshot(self) -> list[dict]:
        return [{"proxy": s.label, "ok": s.successes, "consecutive_failures": s.failures} for s in self._states]
