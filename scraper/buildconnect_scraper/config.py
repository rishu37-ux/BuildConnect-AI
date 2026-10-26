from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    api_url: str = "http://localhost:4000/api"
    ingest_api_key: str = ""
    proxies: list[str] = field(default_factory=list)
    user_agent: str = "BuildConnectBot/0.1 (+https://example.com/bot)"
    # Politeness: at most one request per domain every `min_delay` seconds.
    min_delay: float = 2.0
    concurrency: int = 4
    timeout: float = 20.0
    max_retries: int = 3
    respect_robots: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            api_url=env("BC_API_URL", cls.api_url),
            ingest_api_key=env("BC_INGEST_API_KEY", ""),
            proxies=[p.strip() for p in env("BC_PROXIES", "").split(",") if p.strip()],
            user_agent=env("BC_USER_AGENT", cls.user_agent),
            min_delay=float(env("BC_MIN_DELAY", cls.min_delay)),
            concurrency=int(env("BC_CONCURRENCY", cls.concurrency)),
            timeout=float(env("BC_TIMEOUT", cls.timeout)),
            max_retries=int(env("BC_MAX_RETRIES", cls.max_retries)),
            respect_robots=env("BC_RESPECT_ROBOTS", "true").lower() != "false",
        )
