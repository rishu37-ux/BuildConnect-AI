import httpx
import pytest

from buildconnect_scraper.agent import LeadAgent
from buildconnect_scraper.config import Settings
from buildconnect_scraper.fetcher import AccessChallenge, Fetcher, detect_challenge
from buildconnect_scraper.models import ScrapeGoal
from buildconnect_scraper.proxy import ProxyPool

HTML = {"content-type": "text/html; charset=utf-8"}


def test_proxy_pool_rotates_and_cools_down():
    now = [0.0]
    pool = ProxyPool(["http://a:1", "http://b:2"], base_cooldown=10, clock=lambda: now[0])
    a = pool.acquire()
    b = pool.acquire()
    assert {a.url, b.url} == {"http://a:1", "http://b:2"}
    pool.report_failure(a)
    assert all(pool.acquire() is b for _ in range(3))
    now[0] = 11
    assert any(pool.acquire() is a for _ in range(2))
    assert ProxyPool([]).acquire().label == "direct"


def test_detect_challenge_vs_contact_form():
    challenge = httpx.Response(403, headers=HTML, text="<script src='/cdn-cgi/challenge-platform/x'></script>")
    assert detect_challenge(challenge)
    wall = httpx.Response(200, headers=HTML, text="<div class='g-recaptcha'></div>")
    assert detect_challenge(wall) == "captcha wall"
    body = "<p>" + "Our architecture practice in Shimla designs homes. " * 30 + "</p>"
    form = httpx.Response(200, headers=HTML, text=body + "<form><div class='g-recaptcha'></div></form>")
    assert detect_challenge(form) is None


def _site(pages: dict[str, tuple[int, str]], hits: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode()
        hits.append(f"{request.url.host}{path}")
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        status, body = pages.get(f"{request.url.host}{path}", (404, "not found"))
        return httpx.Response(status, headers=HTML, text=body)
    return handler


class MemorySink:
    def __init__(self):
        self.leads, self.started, self.finished = [], None, None

    async def start(self, agent_name, target):
        self.started = target

    async def add(self, lead):
        self.leads.append(lead)

    async def finish(self, pages_fetched, leads_found, stats):
        self.finished = stats


@pytest.fixture
def settings():
    return Settings(min_delay=0, max_retries=2, proxies=["http://p1:8080", "http://p2:8080"])


async def test_agent_crawls_follows_pagination_and_respects_robots(settings):
    page1 = """<html><head><title>Structural engineers in Shimla</title></head><body>
      <div><h4>Er. Rakesh Thakur</h4><p>Structural consultant, Shimla, Himachal Pradesh. 94180 00001</p></div>
      <a href="/list?page=2">Next</a> <a href="/private/admin">Admin</a>
      <a href="https://facebook.com/x">FB</a> <a href="https://other.example/">Other site</a></body></html>"""
    page2 = """<html><head><title>Structural engineers in Shimla - page 2</title></head><body>
      <div><h4>Er. Anjali Verma</h4><p>Structural engineer, Solan. anjali@verma-struct.in</p></div>
      <div><h4>Er. Mohit Rana</h4><p>Structural engineer, Pune. 99999 88888</p></div></body></html>"""
    hits: list[str] = []
    transport = httpx.MockTransport(_site({"dir.example.in/list": (200, page1),
                                           "dir.example.in/list?page=2": (200, page2)}, hits))
    fetcher = Fetcher(settings, client_factory=lambda proxy: httpx.AsyncClient(transport=transport))
    sink = MemorySink()

    summary = await LeadAgent(ScrapeGoal(max_pages=10), settings, sink, fetcher).run(["https://dir.example.in/list"])

    names = sorted(lead.full_name for lead in sink.leads)
    assert names == ["Er. Anjali Verma", "Er. Rakesh Thakur"]  # Pune lead filtered out by state
    assert "dir.example.in/private/admin" not in hits
    assert not any("other.example" in h or "facebook" in h for h in hits)
    assert summary["pages_fetched"] == 2 and summary["leads_found"] == 2
    assert sink.finished is not None


async def test_agent_stops_on_captcha_instead_of_rotating(settings):
    hits: list[str] = []
    wall = "<html><body><div class='h-captcha'></div></body></html>"
    transport = httpx.MockTransport(_site({"blocked.example/": (200, wall)}, hits))
    fetcher = Fetcher(settings, client_factory=lambda proxy: httpx.AsyncClient(transport=transport))
    sink = MemorySink()

    summary = await LeadAgent(ScrapeGoal(), settings, sink, fetcher).run(["https://blocked.example/"])

    assert summary["blocked_domains"] == {"blocked.example": "captcha wall"}
    assert hits.count("blocked.example/") == 1  # no retry through another proxy
    assert sink.leads == []


async def test_fetch_rotates_proxy_on_transport_error(settings):
    calls = []

    def factory(proxy):
        def handler(request):
            calls.append(proxy)
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            if proxy == "http://p1:8080":
                raise httpx.ConnectError("proxy down")
            return httpx.Response(200, headers=HTML, text="<html>ok</html>")
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    fetcher = Fetcher(settings, client_factory=factory)
    fetcher._backoff = staticmethod(lambda attempt: _noop())
    page = await fetcher.fetch("https://site.example/a")
    assert page.proxy == "p2:8080"
    with pytest.raises(AccessChallenge):
        fetcher._clients["http://p2:8080"] = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(403, headers=HTML, text="denied")))
        await fetcher.fetch("https://site.example/b")


async def _noop():
    return None
