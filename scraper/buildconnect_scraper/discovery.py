"""Discovery agent: turns a campaign goal into a ranked list of websites to crawl.

It plans search queries (profession x city), runs them through a search API,
throws away aggregators/social networks/listicles, scores each result for
relevance to the goal, and goes deeper (next result page) only on queries
that are paying off.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .extractors import classify_profession
from .geo import locate
from .models import Profession, ScrapeGoal, State
from .search import SearchError, SearchProvider, SearchResult

log = logging.getLogger(__name__)

QUERY_TEMPLATES: dict[Profession, list[str]] = {
    Profession.ARCHITECT: ["architects in {city}", "architecture firm {city} contact"],
    Profession.STRUCTURAL_ENGINEER: ["structural engineer in {city}", "structural consultant {city} contact"],
    Profession.CONTRACTOR: ["building contractor in {city}", "construction company {city} contact",
                            "builders and developers {city}"],
}

DEFAULT_CITIES: dict[State, list[str]] = {
    State.PUNJAB: ["Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Mohali", "Bathinda", "Hoshiarpur",
                   "Pathankot", "Moga", "Phagwara", "Zirakpur", "Kharar"],
    State.HIMACHAL_PRADESH: ["Shimla", "Mandi", "Solan", "Dharamshala", "Kullu", "Hamirpur", "Una",
                             "Baddi", "Palampur", "Nahan", "Manali", "Bilaspur"],
    State.CHANDIGARH: ["Chandigarh"],
}

# Aggregators, marketplaces, social networks and other sites that either forbid
# automated collection or don't publish professionals' own contact pages.
EXCLUDED_DOMAINS = re.compile(
    r"(^|\.)(justdial|indiamart|sulekha|tradeindia|exportersindia|magicbricks|99acres|housing|nobroker|"
    r"makaan|commonfloor|squareyards|houzz|urbancompany|urbanclap|facebook|instagram|linkedin|twitter|x|"
    r"youtube|pinterest|quora|reddit|wikipedia|google|bing|yelp|glassdoor|naukri|indeed|shine|"
    r"timesofindia|indiatimes|hindustantimes|tribuneindia|ndtv|amazon|flipkart|olx|quikr|zaubacorp|"
    r"tofler|wikimapia|mapsofindia|asklaila|grotal|yellowpages|threebestrated|clutch|designcafe|"
    r"livspace|homelane|nobrokerhood|whatsapp|wa)\.[a-z.]+$"
    r"|\.(gov|nic|gov\.in|nic\.in|edu|ac\.in)$",
    re.I,
)
LISTICLE = re.compile(r"\b(top|best)\s+\d+|\b\d+\s+best\b|\blist of\b|\bnear me\b", re.I)


@dataclass
class Candidate:
    url: str
    domain: str
    title: str
    query: str
    score: float

    @property
    def seeds(self) -> list[str]:
        parts = urlsplit(self.url)
        root = f"{parts.scheme}://{parts.netloc}/"
        return list(dict.fromkeys([self.url, root]))


@dataclass
class DiscoveryStats:
    queries: int = 0
    results: int = 0
    excluded: int = 0
    irrelevant: int = 0
    errors: list[str] = field(default_factory=list)


def domain_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


class DiscoveryAgent:
    def __init__(self, provider: SearchProvider, goal: ScrapeGoal, cities: list[str] | None = None,
                 max_queries: int = 60, min_score: float = 1.0, patience: int = 8):
        self.provider = provider
        self.goal = goal
        self.cities = cities or [c for s in goal.states for c in DEFAULT_CITIES.get(s, [])]
        self.max_queries = max_queries
        self.min_score = min_score
        # Stop after this many consecutive queries that add no new site: search
        # API calls cost money, and the remaining queries are unlikely to help.
        self.patience = patience
        self.stats = DiscoveryStats()

    def plan_queries(self) -> list[str]:
        """Interleave cities and professions so even a small budget covers the whole goal."""
        per_template = [
            [t.format(city=city) for city in self.cities]
            for prof in sorted(self.goal.professions, key=lambda p: p.value)
            for t in QUERY_TEMPLATES.get(prof, [])
        ]
        queries = []
        for i in range(max((len(q) for q in per_template), default=0)):
            for group in per_template:
                if i < len(group):
                    queries.append(group[i])
        return queries[: self.max_queries]

    def score(self, result: SearchResult) -> float | None:
        domain = domain_of(result.url)
        if not domain or EXCLUDED_DOMAINS.search(domain) or result.url.lower().endswith(".pdf"):
            self.stats.excluded += 1
            return None
        text = f"{result.title} {result.snippet}"
        if LISTICLE.search(result.title):
            self.stats.excluded += 1
            return None
        profession, strength = classify_profession(f"{text} {domain.replace('-', ' ')}")
        if profession not in self.goal.professions:
            self.stats.irrelevant += 1
            return None
        city, _, state = locate(text)
        if state is State.OTHER and city is not None:  # explicitly about another region
            self.stats.irrelevant += 1
            return None
        score = 1.0 + strength
        if state in self.goal.states:
            score += 1.0
        if re.search(r"contact|about|team|our work|projects", f"{result.url} {result.title}", re.I):
            score += 0.3
        if score < self.min_score:
            self.stats.irrelevant += 1
            return None
        return score

    async def discover(self, limit: int, skip_domains: set[str] | None = None) -> list[Candidate]:
        best: dict[str, Candidate] = {}
        skip = skip_domains or set()
        target = int(limit * 1.5) + 5  # over-collect a little; some sites will be skipped or empty
        fruitless = 0

        for query in self.plan_queries():
            if len(best) >= target:
                break
            if fruitless >= self.patience:
                log.info("stopping discovery: %d searches in a row found no new sites", fruitless)
                break
            before = len(best)
            for page in range(2):
                try:
                    results = await self.provider.search(query, count=20, offset=page * 20)
                except Exception as exc:  # one failed query shouldn't kill the campaign
                    self.stats.errors.append(f"{query}: {exc}")
                    log.warning("search failed for %r: %s", query, exc)
                    if len(self.stats.errors) >= 5 and not best:
                        raise SearchError(f"search keeps failing: {exc}") from exc
                    break
                self.stats.queries += 1
                self.stats.results += len(results)
                relevant = 0
                for r in results:
                    s = self.score(r)
                    if s is None:
                        continue
                    relevant += 1
                    d = domain_of(r.url)
                    if d in skip:
                        continue
                    if d not in best or s > best[d].score:
                        best[d] = Candidate(r.url, d, r.title, query, s)
                # Only dig into page 2 when this query is mostly on-target.
                if not results or relevant < len(results) / 2:
                    break
            fruitless = fruitless + 1 if len(best) == before else 0
            log.info("query %r -> %d candidate sites so far", query, len(best))

        ranked = sorted(best.values(), key=lambda c: -c.score)
        return ranked[: target]
