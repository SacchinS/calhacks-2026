"""Load demo vocabulary into the autocomplete memory, and time the startup load.

    uv run python tools/seed_vocab.py                 # demo words into vocab.sqlite (make demo)
    uv run python tools/seed_vocab.py --mock          # ... into vocab-mock.sqlite (make mock)
    uv run python tools/seed_vocab.py --synthetic 500 --time   # 500 made-up words, then time
                                                      # building the search like the engine does
    uv run python tools/seed_vocab.py --bench 50      # time P-R -> Priyanka and F-I -> Figma
    uv run python tools/seed_vocab.py --list
    uv run python tools/seed_vocab.py --reset         # delete every remembered word

The demo words: Julian (tennis, three weeks ago), Jupyter (data work, recent), June, and a
few more, so J-U ranks differently with a tennis or a data conversation. Priyanka and
Kubernetes aren't seeded: the mock captions teach them in the demo.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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


def percentile(values: list[float], fraction: float) -> float:
    """The nearest-rank percentile, so p95 of 50 samples is a sample, not an average."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def demo_captions() -> list[str]:
    path = ROOT / "fixtures/captions_sample.txt"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


async def bench(config, rounds: int, path: Path) -> None:
    """Spell P-R and F-I `rounds` times each against the demo call, and report the latency the
    pitch quotes. The words come from the demo list plus the captions, exactly as in a call:
    Priyanka and Figma are learned from what the other side says."""
    import contextlib

    from app import load_class
    from language.autocomplete import Autocompleter
    from language.tagger import MockTagger
    from shared.bus import Bus
    from shared.events import Caption

    store = VocabStore(path)
    store.add(demo_occurrences())
    search = load_class("vocab_search", config.vocab_search)(config)
    # The mock tagger keeps the bench offline: tags only reach the search documents, and the
    # demo words carry theirs already.
    ac = Autocompleter(Bus(), config, store, search, MockTagger())

    started = time.monotonic()
    await ac.start()
    for _ in range(6000):  # the search builds in a background task
        if ac.search_ready or not ac._tasks:
            break
        await asyncio.sleep(0.01)
    build_ms = (time.monotonic() - started) * 1000
    if not ac.search_ready:
        print(f"{search.name} search didn't start; ranking on letters alone")

    captions = demo_captions()
    for line in captions:
        ac.bus.publish(Caption(line, is_final=True))
    for _ in range(500):  # the words the other side said are learned in the background
        if ac.store.for_term("PRIYANKA") and ac.store.for_term("FIGMA"):
            break
        await asyncio.sleep(0.01)
    ac.stats = build_stats(ac.store.all(), ac.transcript_weight)

    results: dict[str, dict[str, list]] = {
        word: {"latency": [], "search": [], "top": []} for word in ("Priyanka", "Figma")
    }
    for _ in range(rounds):
        for word, letters in (("Priyanka", "PR"), ("Figma", "FI")):
            # The last ~30 seconds of the call, as the engine holds it while the signer spells.
            ac.conversation.clear()
            for line in captions:
                ac._remember_text(line)
            ac.clear()
            for letter in letters:
                ac.add(letter)
            if ac._suggesting is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await ac._suggesting
            row = results[word]
            if ac.latency_ms is not None:
                row["latency"].append(ac.latency_ms)
            if ac.search_ms is not None and ac.last_search == search.name:
                row["search"].append(ac.search_ms)
            row["top"].append(ac.suggestions[0].term if ac.suggestions else "")
    ac.clear()

    print(f"\n{search.name} search, {rounds} rounds each, {len(ac.stats)} words remembered")
    print(f"startup build: {build_ms:.0f} ms")
    for word, letters in (("Priyanka", "P-R"), ("Figma", "F-I")):
        row = results[word]
        hits = sum(top == word for top in row["top"])
        print(f"\n{letters} -> {word}: top suggestion {hits}/{len(row['top'])} rounds")
        for label, key in (("letter to suggestion", "latency"), (f"{search.name} query", "search")):
            samples = row[key]
            if samples:
                p50, p95 = percentile(samples, 0.5), percentile(samples, 0.95)
                print(f"  {label}: p50 {p50:.1f} ms, p95 {p95:.1f} ms  (n={len(samples)})")
            else:
                print(f"  {label}: no samples")
    await ac.stop()
    store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mock", action="store_true", help="the file make mock uses")
    parser.add_argument("--db", help="a different SQLite file")
    parser.add_argument("--synthetic", type=int, default=0, help="add N made-up words instead")
    parser.add_argument("--time", action="store_true", help="time the startup search build")
    parser.add_argument(
        "--bench",
        type=int,
        nargs="?",
        const=50,
        default=0,
        metavar="N",
        help="spell P-R and F-I N times each (default 50) and report the latency",
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    config = load_config() if args.mock else load_config(overlay="config.demo.yaml")
    if args.bench:
        # Never the real memory: the bench writes demo words and whatever the captions teach.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(args.db) if args.db else Path(tmp) / "vocab-bench.sqlite"
            asyncio.run(bench(config, args.bench, path))
        return

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
