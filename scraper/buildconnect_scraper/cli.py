from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .agent import LeadAgent
from .config import Settings
from .models import Profession, ScrapeGoal, State
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
    p = argparse.ArgumentParser(prog="buildconnect-scrape", description=__doc__)
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
