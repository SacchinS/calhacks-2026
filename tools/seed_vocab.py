"""Load demo vocabulary into the autocomplete memory, and time the startup load.

    uv run python tools/seed_vocab.py                 # demo words into vocab.sqlite (make demo)
    uv run python tools/seed_vocab.py --mock          # ... into vocab-mock.sqlite (make mock)
    uv run python tools/seed_vocab.py --synthetic 500 --time   # 500 made-up words, then time
                                                      # building the search like the engine does
    uv run python tools/seed_vocab.py --list
    uv run python tools/seed_vocab.py --reset         # delete every remembered word

The demo words: Julian (tennis, three weeks ago), Jupyter (data work, recent), June, and a
few more, so J-U ranks differently with a tennis or a data conversation. Priyanka and
Kubernetes aren't seeded: the mock captions teach them in the demo.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from language.vocab import Occurrence, VocabStore, build_stats, vocab_path  # noqa: E402
from shared.config import load_config  # noqa: E402

DAY = 86400

DEMO = [
    ("Julian", "name", 21, ("tennis", "doubles partner", "weekend")),
    ("Jupyter", "term", 2, ("notebooks", "data analysis", "python")),
    ("Jupyter", "term", 4, ("notebooks", "data analysis", "charts")),
    ("Jupyter", "term", 6, ("data analysis", "survey results")),
    ("June", "name", 10, ("calendar", "summer", "vacation")),
    ("June", "name", 12, ("calendar", "planning")),
    ("API", "acronym", 1, ("backend", "integration", "software")),
    ("Figma", "term", 3, ("design", "mockups", "dashboard")),
    ("Marisol", "name", 5, ("design review", "dashboard", "team")),
]


def demo_occurrences() -> list[Occurrence]:
    now = time.time()
    return [
        Occurrence(term, kind, "fingerspelled", used_at=now - days * DAY, tags=tags)
        for term, kind, days, tags in DEMO
    ]


def synthetic(n: int) -> list[Occurrence]:
    topics = [
        ("tennis", "doubles"),
        ("data analysis", "notebooks"),
        ("cooking", "recipes"),
        ("deploys", "infrastructure"),
        ("budget", "finance"),
        ("hiring", "interviews"),
    ]
    now = time.time()
    return [
        Occurrence(
            f"Word{chr(65 + i % 26)}{chr(65 + (i // 26) % 26)}{i}",
            "term",
            "fingerspelled",
            used_at=now - (i % 60) * DAY,
            tags=topics[i % len(topics)],
        )
        for i in range(n)
    ]


async def time_search(config, occurrences: list[Occurrence]) -> None:
    from app import load_class

    search = load_class("vocab_search", config.vocab_search)(config)
    start = time.monotonic()
    try:
        await search.open(occurrences)
    except Exception as exc:
        print(f"{search.name} search can't start: {exc}")
        return
    seconds = time.monotonic() - start
    print(f"{search.name} search: {len(occurrences)} occurrences ready in {seconds * 1000:.0f} ms")
    start = time.perf_counter()
    scores = await search.context("tennis doubles this weekend", "prefix2", ["JU", "WO"])
    print(f"one context query: {(time.perf_counter() - start) * 1000:.1f} ms, {len(scores)} words")
    await search.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mock", action="store_true", help="the file make mock uses")
    parser.add_argument("--db", help="a different SQLite file")
    parser.add_argument("--synthetic", type=int, default=0, help="add N made-up words instead")
    parser.add_argument("--time", action="store_true", help="time the startup search build")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    config = load_config() if args.mock else load_config(overlay="config.demo.yaml")
    path = Path(args.db) if args.db else vocab_path(config)
    store = VocabStore(path)
    if args.reset:
        store.delete([o.id for o in store.all()])
        print(f"cleared {path}")
    elif args.list:
        for st in sorted(build_stats(store.all()).values(), key=lambda s: -s.last_used):
            print(f"{st.term:20} {st.kind:8} used {st.count:g}x  {', '.join(st.tags)}")
    else:
        occurrences = synthetic(args.synthetic) if args.synthetic else demo_occurrences()
        store.add(occurrences)
        print(f"added {len(occurrences)} occurrences to {path}")
    if args.time:
        asyncio.run(time_search(config, store.all()))
    store.close()


if __name__ == "__main__":
    main()
