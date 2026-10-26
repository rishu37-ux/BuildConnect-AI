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
    # Campaign worker
    search_provider: str = "brave"
    search_api_key: str = ""
    search_file: str | None = None
    crawler_agents: int = 3
    poll_interval: float = 10.0
    recrawl_after_days: int = 30

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
            search_provider=env("BC_SEARCH_PROVIDER", cls.search_provider),
            search_api_key=env("BC_SEARCH_API_KEY", ""),
            search_file=env("BC_SEARCH_FILE") or None,
            crawler_agents=int(env("BC_CRAWLER_AGENTS", cls.crawler_agents)),
            poll_interval=float(env("BC_POLL_INTERVAL", cls.poll_interval)),
            recrawl_after_days=int(env("BC_RECRAWL_AFTER_DAYS", cls.recrawl_after_days)),
        )
