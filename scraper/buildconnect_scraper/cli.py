from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .agent import LeadAgent
from .campaign import run_worker
from .config import Settings
from .discovery import DiscoveryAgent
from .models import Profession, ScrapeGoal, State
from .search import build_provider
from .sink import ApiSink, JsonlSink


def _read_seeds(args) -> list[str]:
    seeds = list(args.seed or [])
    if args.seeds_file:
        for line in Path(args.seeds_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                seeds.append(line)
    return list(dict.fromkeys(seeds))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="buildconnect-scrape",
        description="Crawl given seed URLs. Other commands: `worker` (run dashboard campaigns), "
                    "`discover` (preview sites the discovery agent would find).",
    )
    p.add_argument("--seed", action="append", help="Seed URL (repeatable)")
    p.add_argument("--seeds-file", help="File with one seed URL per line")
    p.add_argument("--profession", action="append", choices=[x.value for x in Profession if x is not Profession.OTHER],
                   help="Target profession (repeatable; default: all three)")
    p.add_argument("--state", action="append", choices=[s.value for s in State if s is not State.OTHER],
                   help="Target state (repeatable; default: punjab, himachal_pradesh)")
    p.add_argument("--max-pages", type=int, default=200)
    p.add_argument("--max-depth", type=int, default=3)
    p.add_argument("--min-confidence", type=float, default=0.4)
    p.add_argument("--dry-run", metavar="FILE", help="Write leads to a JSONL file instead of the API")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)


def worker_main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="buildconnect-scrape worker",
                                description="Run queued campaigns from the dashboard (discovery + crawler agents)")
    p.add_argument("--once", action="store_true", help="Exit when no campaign is queued")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    _setup_logging(args.verbose)
    asyncio.run(run_worker(Settings.from_env(), once=args.once))
    return 0


def discover_main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="buildconnect-scrape discover",
                                description="Preview which websites the discovery agent would crawl")
    p.add_argument("--profession", action="append", choices=[x.value for x in Profession if x is not Profession.OTHER])
    p.add_argument("--state", action="append", choices=[s.value for s in State if s is not State.OTHER])
    p.add_argument("--city", action="append", help="City to search (repeatable; default: major cities of the states)")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--max-queries", type=int, default=10)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    _setup_logging(args.verbose)

    goal = ScrapeGoal()
    if args.profession:
        goal.professions = {Profession(x) for x in args.profession}
    if args.state:
        goal.states = {State(x) for x in args.state}
    settings = Settings.from_env()

    async def go():
        provider = build_provider(settings.search_provider, settings.search_api_key, settings.search_file)
        try:
            agent = DiscoveryAgent(provider, goal, cities=args.city, max_queries=args.max_queries)
            sites = await agent.discover(limit=args.limit)
            for c in sites:
                print(f"{c.score:4.1f}  {c.domain:40.40}  {c.title[:60]}")
            print(f"\n{len(sites)} sites from {agent.stats.queries} searches "
                  f"({agent.stats.excluded} aggregators/social excluded, {agent.stats.irrelevant} off-target)")
        finally:
            await provider.aclose()

    asyncio.run(go())
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "worker":
        return worker_main(argv[1:])
    if argv and argv[0] == "discover":
        return discover_main(argv[1:])
    if argv and argv[0] == "crawl":
        argv = argv[1:]
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    seeds = _read_seeds(args)
    if not seeds:
        print("No seed URLs given (use --seed or --seeds-file).")
        return 2

    goal = ScrapeGoal(max_pages=args.max_pages, max_depth=args.max_depth, min_confidence=args.min_confidence)
    if args.profession:
        goal.professions = {Profession(p) for p in args.profession}
    if args.state:
        goal.states = {State(s) for s in args.state}

    settings = Settings.from_env()
    sink = JsonlSink(args.dry_run) if args.dry_run else ApiSink(settings)
    summary = asyncio.run(LeadAgent(goal, settings, sink).run(seeds))
    print(json.dumps(summary, indent=2))
    return 0
