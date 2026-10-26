"""Web search providers used by the discovery agent.

Uses official search APIs (not scraping of search-engine result pages):

* ``brave``   — Brave Search API      (BC_SEARCH_API_KEY from https://brave.com/search/api/)
* ``serpapi`` — SerpAPI Google search (BC_SEARCH_API_KEY from https://serpapi.com/)
* ``static``  — a local JSON file mapping query -> [urls] (BC_SEARCH_FILE), for tests and
  for feeding a hand-picked list of sites through the same pipeline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""


class SearchError(Exception):
    pass


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, count: int = 20, offset: int = 0) -> list[SearchResult]: ...

    async def aclose(self) -> None: ...


class BraveSearch:
    name = "brave"
    URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=20)
        self._headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}

    async def search(self, query: str, count: int = 20, offset: int = 0) -> list[SearchResult]:
        count = min(count, 20)
        # Brave's `offset` is a page index (0-9), not a result index.
        resp = await self._client.get(self.URL, headers=self._headers, params={
            "q": query, "country": "IN", "search_lang": "en", "count": count, "offset": min(offset // count, 9),
        })
        if resp.status_code != 200:
            raise SearchError(f"Brave search failed ({resp.status_code}): {resp.text[:200]}")
        items = resp.json().get("web", {}).get("results", [])
        return [SearchResult(i["url"], i.get("title", ""), i.get("description", "")) for i in items if i.get("url")]

    async def aclose(self) -> None:
        await self._client.aclose()


class SerpApiSearch:
    name = "serpapi"
    URL = "https://serpapi.com/search.json"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=30)
        self._key = api_key

    async def search(self, query: str, count: int = 20, offset: int = 0) -> list[SearchResult]:
        resp = await self._client.get(self.URL, params={
            "engine": "google", "q": query, "gl": "in", "hl": "en", "num": count, "start": offset,
            "api_key": self._key,
        })
        if resp.status_code != 200:
            raise SearchError(f"SerpAPI search failed ({resp.status_code}): {resp.text[:200]}")
        items = resp.json().get("organic_results", [])
        return [SearchResult(i["link"], i.get("title", ""), i.get("snippet", "")) for i in items if i.get("link")]

    async def aclose(self) -> None:
        await self._client.aclose()


class StaticSearch:
    """Results from a JSON file: {"query": ["url", ...], "*": ["url", ...]}. "*" matches every query."""

    name = "static"

    def __init__(self, path: str | Path):
        self._data: dict[str, list] = json.loads(Path(path).read_text(encoding="utf-8"))

    async def search(self, query: str, count: int = 20, offset: int = 0) -> list[SearchResult]:
        if offset:
            return []
        items = self._data.get(query, []) + self._data.get("*", [])
        out = []
        for item in items[:count]:
            if isinstance(item, str):
                out.append(SearchResult(item))
            else:
                out.append(SearchResult(item["url"], item.get("title", ""), item.get("snippet", "")))
        return out

    async def aclose(self) -> None:
        return None


def build_provider(name: str, api_key: str, static_file: str | None = None) -> SearchProvider:
    name = (name or "").lower()
    if name == "static":
        if not static_file:
            raise SearchError("BC_SEARCH_FILE is required for the static search provider")
        return StaticSearch(static_file)
    if not api_key:
        raise SearchError(
            "No search API key configured. Set BC_SEARCH_PROVIDER (brave or serpapi) and BC_SEARCH_API_KEY in .env"
        )
    if name == "brave":
        return BraveSearch(api_key)
    if name == "serpapi":
        return SerpApiSearch(api_key)
    raise SearchError(f"Unknown search provider {name!r} (use brave, serpapi or static)")
