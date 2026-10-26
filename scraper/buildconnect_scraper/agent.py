"""The primary lead-discovery agent.

The agent runs an observe → extract → decide loop over a priority frontier:

* **Observe**: fetch a page (politely, via the rotating proxy pool).
* **Extract**: pull candidate leads and keep those matching the goal
  (profession, state, minimum confidence).
* **Decide**: score every outgoing link for how likely it is to lead to more
  matching contacts, using the goal's vocabulary, the gazetteer, and what the
  agent has learned this run: URL path patterns and domains that produced
  leads get boosted, domains that yield nothing are abandoned, and domains
  that challenge or block the crawler are dropped entirely.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .config import Settings
from .extractors import extract_leads
from .fetcher import AccessChallenge, DisallowedByRobots, Fetcher, FetchError
from .geo import HIMACHAL_DISTRICTS, PUNJAB_DISTRICTS
from .models import Lead, Profession, ScrapeGoal, State
from .sink import LeadSink

log = logging.getLogger(__name__)

_PROFESSION_TERMS = {
    Profession.ARCHITECT: ["architect", "architecture", "coa", "iia"],
    Profession.STRUCTURAL_ENGINEER: ["structural", "engineer", "consultant", "civil"],
    Profession.CONTRACTOR: ["contractor", "builder", "construction", "developer", "infra"],
}
_LISTING_TERMS = ["directory", "member", "members", "listing", "list", "team", "people", "profile",
                  "contact", "about", "firms", "professionals", "search", "category", "city"]
_PAGINATION = re.compile(r"[?&](page|p|pg|start|offset)=\d+|/page/\d+|\bnext\b|»|›", re.I)
_SKIP = re.compile(
    r"\.(pdf|jpe?g|png|gif|webp|svg|zip|rar|docx?|xlsx?|pptx?|mp4|mp3)(\?|$)"
    r"|/(login|signin|signup|register|cart|checkout|wp-admin|wp-login|privacy|terms|careers|jobs)\b"
    r"|[?&](share|replytocom|add-to-cart)=",
    re.I,
)
_SOCIAL = re.compile(r"(facebook|instagram|twitter|x|linkedin|youtube|pinterest|wa)\.(com|me)$", re.I)


@dataclass(order=True)
class _Task:
    priority: float
    seq: int
    url: str = field(compare=False)
    depth: int = field(compare=False)


@dataclass
class DomainStats:
    pages: int = 0
    leads: int = 0
    blocked: str | None = None

    @property
    def yield_rate(self) -> float:
        return self.leads / self.pages if self.pages else 0.0


class LeadAgent:
    name = "lead-discovery-agent"

    def __init__(self, goal: ScrapeGoal, settings: Settings, sink: LeadSink, fetcher: Fetcher | None = None,
                 allowed_domains: set[str] | None = None, abandon_after: int = 15):
        self.goal = goal
        self.settings = settings
        self.sink = sink
        self.fetcher = fetcher or Fetcher(settings)
        self.allowed_domains = allowed_domains
        self.abandon_after = abandon_after

        self._frontier: list[_Task] = []
        self._seq = itertools.count()
        self._seen_urls: set[str] = set()
        self._seen_leads: set[str] = set()
        self._domains: dict[str, DomainStats] = defaultdict(DomainStats)
        self._productive_paths: Counter[str] = Counter()
        self.pages_fetched = 0
        self.leads_found = 0
        self.errors: Counter[str] = Counter()

        self._goal_terms = [t for p in goal.professions for t in _PROFESSION_TERMS.get(p, [])]
        places: list[str] = []
        if State.PUNJAB in goal.states:
            places += ["punjab", "chandigarh", "mohali"] + [d.lower() for d in PUNJAB_DISTRICTS]
        if State.HIMACHAL_PRADESH in goal.states:
            places += ["himachal"] + [d.lower() for d in HIMACHAL_DISTRICTS]
        self._place_terms = places

    # -- decide ------------------------------------------------------------

    @staticmethod
    def _path_pattern(url: str) -> str:
        """Coarse URL shape, e.g. /members/123/ravi -> /members/*/*."""
        parts = [p for p in urlsplit(url).path.split("/") if p]
        return "/" + "/".join([parts[0], *["*"] * (len(parts) - 1)]) if parts else "/"

    def score_link(self, url: str, anchor: str, depth: int) -> float | None:
        """Higher is better; None means don't follow."""
        parts = urlsplit(url)
        host = parts.netloc.lower()
        if _SKIP.search(url) or _SOCIAL.search(host.removeprefix("www.")):
            return None
        if self.allowed_domains is not None and host not in self.allowed_domains:
            return None
        stats = self._domains[host]
        if stats.blocked:
            return None
        if stats.pages >= self.abandon_after and stats.leads == 0:
            return None

        haystack = f"{parts.path} {parts.query} {anchor}".lower()
        score = 1.0
        score += 2.0 * sum(term in haystack for term in self._goal_terms)
        score += 1.5 * min(sum(place in haystack for place in self._place_terms), 2)
        score += 1.0 * sum(term in haystack for term in _LISTING_TERMS)
        if _PAGINATION.search(f"{url} {anchor}"):
            score += 3.0
        score += min(self._productive_paths[self._path_pattern(url)], 5) * 1.5
        score += 4.0 * stats.yield_rate
        return score / (1 + depth)

    def _enqueue(self, url: str, depth: int, score: float) -> None:
        if url in self._seen_urls or depth > self.goal.max_depth:
            return
        self._seen_urls.add(url)
        heapq.heappush(self._frontier, _Task(-score, next(self._seq), url, depth))

    # -- extract -------------------------------------------------------------

    def accept(self, lead: Lead) -> bool:
        return (
            lead.profession in self.goal.professions
            and lead.state in self.goal.states
            and lead.confidence >= self.goal.min_confidence
        )

    # -- observe ---------------------------------------------------------------

    async def _process(self, task: _Task) -> None:
        host = urlsplit(task.url).netloc.lower()
        stats = self._domains[host]
        if stats.blocked:
            return
        try:
            page = await self.fetcher.fetch(task.url)
        except AccessChallenge as exc:
            stats.blocked = exc.reason
            self.errors["challenge"] += 1
            log.warning("stopping crawl of %s: %s (consider an official API or manual review)", host, exc.reason)
            return
        except DisallowedByRobots:
            self.errors["robots"] += 1
            return
        except FetchError as exc:
            self.errors["fetch"] += 1
            log.debug("%s", exc)
            return

        self.pages_fetched += 1
        stats.pages += 1
        leads, ctx = extract_leads(page.html, page.url)
        accepted = 0
        for lead in leads:
            if not self.accept(lead) or lead.key() in self._seen_leads:
                continue
            self._seen_leads.add(lead.key())
            await self.sink.add(lead)
            accepted += 1
        if accepted:
            stats.leads += accepted
            self.leads_found += accepted
            self._productive_paths[self._path_pattern(page.url)] += 1
            log.info("%d leads from %s", accepted, page.url)

        for url, anchor in ctx.links:
            score = self.score_link(url, anchor, task.depth + 1)
            if score is not None:
                self._enqueue(url, task.depth + 1, score)

    async def run(self, seeds: list[str]) -> dict:
        if self.allowed_domains is None:
            self.allowed_domains = {urlsplit(s).netloc.lower() for s in seeds}
        for seed in seeds:
            self._enqueue(seed, 0, 100.0)

        await self.sink.start(self.name, {**self.goal.describe(), "seeds": seeds})
        in_flight: set[asyncio.Task] = set()
        try:
            while (self._frontier or in_flight) and self.pages_fetched + len(in_flight) < self.goal.max_pages:
                while self._frontier and len(in_flight) < self.settings.concurrency \
                        and self.pages_fetched + len(in_flight) < self.goal.max_pages:
                    task = heapq.heappop(self._frontier)
                    in_flight.add(asyncio.create_task(self._process(task)))
                if not in_flight:
                    break
                done, in_flight = await asyncio.wait(in_flight, return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    if t.exception():
                        self.errors["internal"] += 1
                        log.exception("task failed", exc_info=t.exception())
            if in_flight:
                await asyncio.gather(*in_flight, return_exceptions=True)
        finally:
            summary = self.summary()
            await self.sink.finish(self.pages_fetched, self.leads_found, summary)
            await self.fetcher.aclose()
        return summary

    def summary(self) -> dict:
        return {
            "pages_fetched": self.pages_fetched,
            "leads_found": self.leads_found,
            "errors": dict(self.errors),
            "blocked_domains": {h: s.blocked for h, s in self._domains.items() if s.blocked},
            "domain_yield": {h: {"pages": s.pages, "leads": s.leads} for h, s in self._domains.items()},
            "proxies": self.fetcher.proxies.snapshot(),
        }
