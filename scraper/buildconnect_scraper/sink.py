"""Where discovered leads go: the BuildConnect API, or a local JSONL file."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

import httpx

from .config import Settings
from .models import Lead

log = logging.getLogger(__name__)


class LeadSink(Protocol):
    async def start(self, agent_name: str, target: dict) -> None: ...
    async def add(self, lead: Lead) -> None: ...
    async def finish(self, pages_fetched: int, leads_found: int, stats: dict) -> None: ...


class ApiSink:
    def __init__(self, settings: Settings, batch_size: int = 100, client: httpx.AsyncClient | None = None,
                 campaign_id: int | None = None):
        if not settings.ingest_api_key:
            raise ValueError("BC_INGEST_API_KEY is required to push leads to the API")
        self._client = client or httpx.AsyncClient(
            base_url=settings.api_url.rstrip("/") + "/", timeout=30,
            headers={"x-api-key": settings.ingest_api_key},
        )
        self._batch: list[Lead] = []
        self._batch_size = batch_size
        self.run_id: int | None = None
        self.campaign_id = campaign_id
        self.totals = {"inserted": 0, "merged": 0, "suppressed": 0, "invalid": 0}

    async def start(self, agent_name: str, target: dict) -> None:
        body = {"agent_name": agent_name, "target": target}
        if self.campaign_id:
            body["campaign_id"] = self.campaign_id
        resp = await self._client.post("ingest/runs", json=body)
        resp.raise_for_status()
        self.run_id = resp.json()["id"]

    async def add(self, lead: Lead) -> None:
        self._batch.append(lead)
        if len(self._batch) >= self._batch_size:
            await self.flush()

    async def flush(self) -> None:
        # Swap the buffer out first: several crawler agents may add leads while we await.
        batch, self._batch = self._batch, []
        if not batch:
            return
        payload = {"leads": [lead.to_payload() for lead in batch]}
        if self.run_id:
            payload["run_id"] = self.run_id
        resp = await self._client.post("ingest/leads", json=payload)
        resp.raise_for_status()
        for k, v in resp.json().items():
            self.totals[k] = self.totals.get(k, 0) + v
        log.info("pushed %d leads: %s", len(batch), resp.json())

    async def finish(self, pages_fetched: int, leads_found: int, stats: dict) -> None:
        await self.flush()
        if self.run_id:
            resp = await self._client.patch(
                f"ingest/runs/{self.run_id}",
                json={"pages_fetched": pages_fetched, "leads_found": leads_found,
                      "stats": {**stats, "ingest": self.totals}},
            )
            resp.raise_for_status()
        await self._client.aclose()


class JsonlSink:
    """Dry-run sink: write leads to a local file for review."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._fh = None

    async def start(self, agent_name: str, target: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")

    async def add(self, lead: Lead) -> None:
        self._fh.write(json.dumps(lead.to_payload(), ensure_ascii=False) + "\n")

    async def finish(self, pages_fetched: int, leads_found: int, stats: dict) -> None:
        if self._fh:
            self._fh.close()
