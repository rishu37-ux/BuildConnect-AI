import httpx

from buildconnect_scraper.campaign import CampaignOrchestrator
from buildconnect_scraper.config import Settings
from buildconnect_scraper.discovery import DiscoveryAgent
from buildconnect_scraper.fetcher import Fetcher
from buildconnect_scraper.models import Profession, ScrapeGoal, State
from buildconnect_scraper.search import SearchResult

HTML = {"content-type": "text/html; charset=utf-8"}


class FakeSearch:
    name = "fake"

    def __init__(self, results: dict[str, list[SearchResult]]):
        self.results = results
        self.queries: list[tuple[str, int]] = []

    async def search(self, query, count=20, offset=0):
        self.queries.append((query, offset))
        return self.results.get(query, []) if offset == 0 else []

    async def aclose(self):
        pass


def test_plan_queries_interleaves_professions_and_cities():
    goal = ScrapeGoal(professions={Profession.ARCHITECT, Profession.STRUCTURAL_ENGINEER})
    agent = DiscoveryAgent(FakeSearch({}), goal, cities=["Ludhiana", "Shimla"], max_queries=4)
    assert agent.plan_queries() == [
        "architects in Ludhiana", "architecture firm Ludhiana contact",
        "structural engineer in Ludhiana", "structural consultant Ludhiana contact",
    ]


async def test_discovery_gives_up_when_searches_stop_paying_off():
    search = FakeSearch({"architects in Ludhiana": [
        SearchResult("https://kaurdesign.in/", "Kaur Design - Architects Ludhiana", "Architecture firm Punjab")]})
    goal = ScrapeGoal(professions={Profession.ARCHITECT}, states={State.PUNJAB})
    agent = DiscoveryAgent(search, goal, cities=["Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Mohali"],
                           max_queries=50, patience=3)
    sites = await agent.discover(limit=30)
    assert [s.domain for s in sites] == ["kaurdesign.in"]
    # 1 productive query (+ its page 2) and 3 fruitless ones, then it stops
    assert len(search.queries) == 5


async def test_discovery_filters_aggregators_listicles_and_other_regions():
    q = "architects in Ludhiana"
    search = FakeSearch({q: [
        SearchResult("https://www.kaurdesign.in/contact", "Kaur Design Studio - Architects in Ludhiana", "Architecture firm"),
        SearchResult("https://www.justdial.com/Ludhiana/Architects", "Architects in Ludhiana - Justdial", "architects"),
        SearchResult("https://blog.example.com/top-10", "Top 10 architects in Ludhiana", "architects Ludhiana"),
        SearchResult("https://pune-arch.in/", "Pune architects studio", "Architect in Pune, Maharashtra"),
        SearchResult("https://bakery.in/", "Ludhiana Bakery", "cakes"),
        SearchResult("https://kaurdesign.in/projects", "Kaur Design projects", "Architecture Ludhiana Punjab"),
    ]})
    goal = ScrapeGoal(professions={Profession.ARCHITECT}, states={State.PUNJAB})
    agent = DiscoveryAgent(search, goal, cities=["Ludhiana"], max_queries=1)
    sites = await agent.discover(limit=10)
    assert [s.domain for s in sites] == ["kaurdesign.in"]
    assert sites[0].seeds[-1] == f"https://{sites[0].url.split('/')[2]}/"
    assert agent.stats.excluded == 2 and agent.stats.irrelevant == 2


class FakeApi:
    def __init__(self, cancel_after_reports: int | None = None):
        self.reports, self.sources, self.updates = [], [], []
        self.cancel_after = cancel_after_reports

    async def report(self, campaign_id, **body):
        self.reports.append(body)
        if self.cancel_after is not None and len(self.reports) > self.cancel_after:
            return "cancelled"
        return body.get("status", "running")

    async def register_sources(self, campaign_id, sources, recrawl_after_days):
        from urllib.parse import urlsplit
        out = []
        for i, s in enumerate(sources, 1):
            domain = urlsplit(s["url"]).hostname.removeprefix("www.")
            out.append({"id": i, "domain": domain, "url": s["url"],
                        "status": "skipped" if domain == "old-firm.in" else "queued"})
        self.sources = out
        return out

    async def update_source(self, source_id, **body):
        self.updates.append((source_id, body))


class MemorySink:
    def __init__(self):
        self.leads = []
        self.totals = {"inserted": 0}

    async def start(self, *a, **k):
        pass

    async def add(self, lead):
        self.leads.append(lead)
        self.totals["inserted"] += 1

    async def finish(self, *a, **k):
        pass


SITES = {
    "arch-one.in": """<html><head><title>Arch One - Architects Ludhiana</title></head><body>
        <div><h3>Ar. Simran Gill</h3><p>Architect, Ludhiana. 98140 11111</p></div>
        <a href="/team">Our team</a></body></html>""",
    "arch-one.in/team": """<html><body><div><h3>Ar. Karan Bedi</h3><p>Ludhiana, Punjab. karan@arch-one.in</p></div></body></html>""",
    "struct-two.in": """<html><head><title>Struct Two Structural Consultants Shimla</title></head><body>
        <div><h3>Er. Neha Thakur</h3><p>Structural consultant, Shimla HP. 94180 22222</p></div></body></html>""",
    "empty-three.in": "<html><head><title>Architects Mohali</title></head><body><p>Coming soon</p></body></html>",
    "walled-four.in": "<html><body><div class='g-recaptcha'></div></body></html>",
}


def _transport():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        key = request.url.host.removeprefix("www.") + request.url.path.rstrip("/")
        body = SITES.get(key)
        return httpx.Response(200, headers=HTML, text=body) if body else httpx.Response(404)
    return httpx.MockTransport(handler)


def _campaign(**over):
    return {"id": 7, "name": "Test", "professions": ["architect", "structural_engineer"],
            "states": ["punjab", "himachal_pradesh"], "cities": ["Ludhiana"], "max_sites": 10,
            "max_pages_per_site": 5, **over}


def _search():
    return FakeSearch({"architects in Ludhiana": [
        SearchResult(f"https://{d}/", f"{d} architects structural Ludhiana", "Architect firm Punjab")
        for d in ["arch-one.in", "struct-two.in", "empty-three.in", "walled-four.in", "old-firm.in"]
    ]})


async def test_orchestrator_runs_parallel_crawler_agents():
    settings = Settings(min_delay=0, crawler_agents=3)
    transport = _transport()
    fetcher = Fetcher(settings, client_factory=lambda proxy: httpx.AsyncClient(transport=transport))
    api, sink = FakeApi(), MemorySink()

    progress = await CampaignOrchestrator(_campaign(), settings, api, _search(), fetcher=fetcher, sink=sink).run()

    assert sorted(lead.full_name for lead in sink.leads) == ["Ar. Karan Bedi", "Ar. Simran Gill", "Er. Neha Thakur"]
    final = {sid: body for sid, body in api.updates if body["status"] != "crawling"}
    by_domain = {s["domain"]: final.get(s["id"], {}).get("status") for s in api.sources}
    assert by_domain == {"arch-one.in": "done", "struct-two.in": "done", "empty-three.in": "no_leads",
                         "walled-four.in": "blocked", "old-firm.in": None}
    assert progress["sites_queued"] == 4 and progress["sites_skipped"] == 1
    assert progress["sites_crawled"] == 4 and progress["leads_found"] == 3 and progress["sites_blocked"] == 1
    assert api.reports[-1]["status"] == "completed"


async def test_orchestrator_stops_when_cancelled():
    settings = Settings(min_delay=0, crawler_agents=1)
    transport = _transport()
    fetcher = Fetcher(settings, client_factory=lambda proxy: httpx.AsyncClient(transport=transport))
    api = FakeApi(cancel_after_reports=1)  # dashboard cancels right after discovery starts

    progress = await CampaignOrchestrator(_campaign(), settings, api, _search(), fetcher=fetcher,
                                          sink=MemorySink()).run()

    assert progress["phase"] == "cancelled"
    assert progress["sites_crawled"] == 0
    assert "status" not in api.reports[-1]  # a cancelled campaign is never marked completed


async def test_brave_provider_request_and_parsing():
    from buildconnect_scraper.search import BraveSearch

    seen = {}

    def handler(request):
        seen.update(dict(request.url.params), token=request.headers["x-subscription-token"])
        return httpx.Response(200, json={"web": {"results": [
            {"url": "https://kaurdesign.in/", "title": "Kaur Design", "description": "Architects Ludhiana"}]}})

    brave = BraveSearch("key-123", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    results = await brave.search("architects in Ludhiana", count=20, offset=20)
    assert results == [SearchResult("https://kaurdesign.in/", "Kaur Design", "Architects Ludhiana")]
    assert seen["offset"] == "1" and seen["country"] == "IN" and seen["token"] == "key-123"
