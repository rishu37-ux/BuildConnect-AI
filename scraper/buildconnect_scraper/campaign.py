"""Autonomous campaigns: a discovery agent plus a team of crawler agents.

    CampaignOrchestrator
      ├─ DiscoveryAgent  – plans search queries, finds & ranks websites
      └─ N × LeadAgent   – crawl one website each, in parallel, sharing the
                           proxy pool, per-domain rate limiter and lead sink

Progress is reported to the backend as a heartbeat, which is also how the
orchestrator learns that someone pressed "Cancel" on the dashboard.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from urllib.parse import urlsplit

import httpx

from .agent import LeadAgent
from .config import Settings
from .discovery import DiscoveryAgent
from .fetcher import Fetcher
from .models import Profession, ScrapeGoal, State
from .search import SearchProvider, build_provider
from .sink import ApiSink

log = logging.getLogger(__name__)


class CampaignApi:
    """Client for the backend's campaign-worker endpoints."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(
            base_url=settings.api_url.rstrip("/") + "/", timeout=30,
            headers={"x-api-key": settings.ingest_api_key},
        )

    async def claim(self, worker_id: str) -> dict | None:
        resp = await self._client.post("ingest/campaigns/claim", json={"worker_id": worker_id})
        resp.raise_for_status()
        return None if resp.status_code == 204 else resp.json()

    async def report(self, campaign_id: int, **body) -> str:
        resp = await self._client.patch(f"ingest/campaigns/{campaign_id}", json=body)
        resp.raise_for_status()
        return resp.json()["status"]

    async def register_sources(self, campaign_id: int, sources: list[dict], recrawl_after_days: int) -> list[dict]:
        resp = await self._client.post(f"ingest/campaigns/{campaign_id}/sources",
                                       json={"sources": sources, "recrawl_after_days": recrawl_after_days})
        resp.raise_for_status()
        return resp.json()

    async def update_source(self, source_id: int, **body) -> None:
        resp = await self._client.patch(f"ingest/sources/{source_id}", json=body)
        resp.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()


class CampaignOrchestrator:
    name = "campaign-orchestrator"

    def __init__(self, campaign: dict, settings: Settings, api: CampaignApi, provider: SearchProvider,
                 fetcher: Fetcher | None = None, sink=None, heartbeat_every: float = 15.0):
        self.campaign = campaign
        self.id = campaign["id"]
        self.settings = settings
        self.api = api
        self.provider = provider
        self.fetcher = fetcher or Fetcher(settings)
        self.sink = sink or ApiSink(settings, batch_size=25, campaign_id=self.id)
        self.heartbeat_every = heartbeat_every
        self.goal = ScrapeGoal(
            professions={Profession(p) for p in campaign["professions"]},
            states={State(s) for s in campaign["states"]},
            max_pages=campaign["max_pages_per_site"],
        )
        self.cancelled = False
        self._agents: set[LeadAgent] = set()
        self.progress: dict = {
            "phase": "starting", "queries_run": 0, "sites_found": 0, "sites_queued": 0, "sites_skipped": 0,
            "sites_crawled": 0, "sites_with_leads": 0, "sites_blocked": 0, "pages_fetched": 0, "leads_found": 0,
            "active_agents": 0,
        }

    async def _heartbeat(self, **extra) -> None:
        status = await self.api.report(self.id, progress=self.progress, **extra)
        if status == "cancelled" and not self.cancelled:
            log.info("campaign %s cancelled from dashboard", self.id)
            self.cancelled = True
            for agent in self._agents:
                agent.stop()

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_every)
            try:
                await self._heartbeat()
            except httpx.HTTPError as exc:
                log.warning("heartbeat failed: %s", exc)

    # -- phase 1: discovery ---------------------------------------------------

    async def discover(self) -> list[dict]:
        self.progress["phase"] = "discovering"
        await self._heartbeat()
        discovery = DiscoveryAgent(self.provider, self.goal, cities=self.campaign.get("cities") or None)
        candidates = await discovery.discover(limit=self.campaign["max_sites"])
        self.progress.update(queries_run=discovery.stats.queries, sites_found=len(candidates))

        registered = await self.api.register_sources(
            self.id, [{"url": c.url, "title": c.title[:500], "query": c.query} for c in candidates],
            self.settings.recrawl_after_days,
        )
        by_domain = {c.domain: c for c in candidates}
        queued = [r for r in registered if r["status"] == "queued"][: self.campaign["max_sites"]]
        for r in queued:
            r["seeds"] = by_domain[r["domain"]].seeds
        self.progress.update(sites_queued=len(queued), sites_skipped=len(registered) - len(queued))
        return queued

    # -- phase 2: crawling --------------------------------------------------------

    async def _crawl_source(self, source: dict) -> None:
        await self.api.update_source(source["id"], status="crawling")
        domain = source["domain"]
        allowed = set()
        for seed in source["seeds"]:
            host = urlsplit(seed).netloc.lower().removeprefix("www.")
            allowed |= {host, f"www.{host}"}
        agent = LeadAgent(self.goal, self.settings, self.sink, self.fetcher, allowed_domains=allowed)
        self._agents.add(agent)
        self.progress["active_agents"] = len(self._agents)
        try:
            await agent.crawl(source["seeds"])
            if agent.blocked_reason:
                status, detail = "blocked", agent.blocked_reason
                self.progress["sites_blocked"] += 1
            elif agent.leads_found:
                status, detail = "done", None
                self.progress["sites_with_leads"] += 1
            elif agent.pages_fetched == 0:
                status, detail = "failed", ", ".join(f"{k}: {v}" for k, v in agent.errors.items()) or "no pages fetched"
            else:
                status, detail = "no_leads", None
        except Exception as exc:  # one bad site must not stop the other agents
            log.exception("crawler agent failed on %s", domain)
            status, detail = "failed", str(exc)[:500]
        finally:
            self._agents.discard(agent)
            self.progress["active_agents"] = len(self._agents)

        self.progress["sites_crawled"] += 1
        self.progress["pages_fetched"] += agent.pages_fetched
        self.progress["leads_found"] += agent.leads_found
        await self.api.update_source(source["id"], status=status, detail=detail,
                                     pages_crawled=agent.pages_fetched, leads_found=agent.leads_found)

    async def crawl(self, sources: list[dict]) -> None:
        self.progress["phase"] = "crawling"
        await self._heartbeat()
        queue: asyncio.Queue[dict] = asyncio.Queue()
        for s in sources:
            queue.put_nowait(s)

        async def crawler_agent(n: int) -> None:
            while not self.cancelled:
                try:
                    source = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                log.info("agent %d crawling %s", n, source["domain"])
                await self._crawl_source(source)

        await asyncio.gather(*(crawler_agent(i + 1) for i in range(max(1, self.settings.crawler_agents))))

    # -- lifecycle ------------------------------------------------------------------

    async def run(self) -> dict:
        started = time.monotonic()
        heartbeat = asyncio.create_task(self._heartbeat_loop())
        await self.sink.start(self.name, {**self.goal.describe(), "campaign": self.campaign["name"]})
        try:
            sources = await self.discover()
            if not self.cancelled:
                await self.crawl(sources)
            self.progress["phase"] = "cancelled" if self.cancelled else "done"
        finally:
            heartbeat.cancel()
            self.progress["active_agents"] = 0
            self.progress["duration_s"] = round(time.monotonic() - started)
            await self.sink.finish(self.progress["pages_fetched"], self.progress["leads_found"],
                                   {"campaign_id": self.id, **self.progress})
            if hasattr(self.sink, "totals"):
                self.progress["leads_new"] = self.sink.totals.get("inserted", 0)
                self.progress["leads_merged"] = self.sink.totals.get("merged", 0)
            await self.fetcher.aclose()
        await self._heartbeat(**({} if self.cancelled else {"status": "completed"}))
        return self.progress


async def run_worker(settings: Settings, once: bool = False) -> None:
    """Poll the backend for queued campaigns and run them one at a time."""
    if not settings.ingest_api_key:
        raise SystemExit("BC_INGEST_API_KEY is required for the worker")
    api = CampaignApi(settings)
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    log.info("campaign worker %s polling %s every %.0fs", worker_id, settings.api_url, settings.poll_interval)
    try:
        while True:
            try:
                campaign = await api.claim(worker_id)
            except httpx.HTTPError as exc:
                log.warning("backend not reachable (%s); retrying", exc)
                campaign = None
            if campaign:
                log.info("starting campaign %s: %s", campaign["id"], campaign["name"])
                provider = None
                try:
                    provider = build_provider(settings.search_provider, settings.search_api_key, settings.search_file)
                    summary = await CampaignOrchestrator(campaign, settings, api, provider).run()
                    log.info("campaign %s finished: %s", campaign["id"], summary)
                except Exception as exc:
                    log.exception("campaign %s failed", campaign["id"])
                    try:
                        await api.report(campaign["id"], status="failed", error=str(exc)[:2000])
                    except httpx.HTTPError:
                        pass
                finally:
                    if provider:
                        await provider.aclose()
                continue
            if once:
                return
            await asyncio.sleep(settings.poll_interval)
    finally:
        await api.aclose()
