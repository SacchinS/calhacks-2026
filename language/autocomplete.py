"""Fingerspelling autocomplete: suggest the word being spelled from the letters so far, the
conversation, and how often and how recently the signer has used each word.

    J-U while talking about tennis      -> Julian (fingerspelled once, weeks ago, at tennis)
    J-U while talking about data        -> Jupyter

Flow: the utterance buffer hands each Letter to `add()`. Suggestions are ranked right away
from the letters, frequency and recency (and the last context scores), then refined with a
context search of the recent conversation (language/vocab_search.py: Moss, or the keyword
mock) and published again as an AutocompleteUpdate. YES accepts the top suggestion (the app
can pick an alternate), NO dismisses them for this word (a second NO drops the letters), and
anything else (a sign, SEND) keeps the letters as spelled. The word goes into the utterance
as one fingerspelled sign; translation, approval and turn-taking are unchanged.

Learning: every accepted or spelled word is recorded (source "fingerspelled"), and likely
names, acronyms and jargon in the other side's final captions too (source "transcript"),
so a word heard in a meeting can be suggested before the signer has ever spelled it.

Memory: rows in a local SQLite file (language/vocab.py) with the word, a few topic tags
(language/tagger.py) and metadata. The conversation itself is only held in memory for
`context_seconds` to query with and to make tags, then dropped.

Score = letters * letter match (1, less per look-alike handshape swap)
      + context * the word's search score, scaled across the candidates
      + frequency * log(1 + uses) / log(1 + most uses among the candidates)
      + recency * 0.5 ** (days since last use / half_life_days)
Weights and the look-alike handshapes are in config.yaml (autocomplete:).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
import uuid
from collections import deque
from typing import Any

from language.tagger import Tagged, make_tagger
from language.vocab import (
    Occurrence,
    TermStats,
    VocabStore,
    build_stats,
    normalize,
    with_tags,
)
from language.vocab_search import VocabSearch
from language.vocab_terms import extract_terms, is_common
from recognition.base import make_sign_event
from shared.bus import Bus
from shared.config import Config
from shared.events import (
    AutocompleteUpdate,
    Caption,
    ModeChanged,
    Notice,
    OutputSent,
    SignEvent,
    Suggestion,
    UtteranceProgress,
)

log = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {"letters": 1.0, "context": 1.0, "frequency": 0.4, "recency": 0.3}
DEFAULT_SIMILAR = ["MN", "UVR", "ASTE"]  # handshapes that are easy to misread for each other


class Autocompleter:
    def __init__(
        self,
        bus: Bus,
        config: Config,
        store: VocabStore,
        search: VocabSearch | None,
        tagger: Any = None,
    ) -> None:
        self.bus = bus
        self.config = config
        self.store = store
        self.search = search
        self.tagger = tagger or make_tagger(config)
        get = lambda key, default: config.get(f"autocomplete.{key}", default)  # noqa: E731
        self.enabled = bool(get("enabled", True))
        self.min_letters = int(get("min_letters", 2))
        self.alternates = int(get("alternates", 2))
        self.weights = {**DEFAULT_WEIGHTS, **(get("weights", {}) or {})}
        self.half_life_days = float(get("half_life_days", 14))
        self.context_seconds = float(get("context_seconds", 30))
        self.context_spread = float(get("context_spread", 0.15))
        self.substitution_penalty = float(get("substitution_penalty", 0.35))
        self.max_substitutions = int(get("max_substitutions", 1))
        self.search_timeout = float(get("search_timeout_ms", 40)) / 1000
        self.transcript_weight = float(get("transcript_weight", 0.5))
        self.transcript_repeat_seconds = float(get("transcript_repeat_seconds", 120))
        self.learn_from_captions = bool(get("learn_from_captions", True))
        self.similar: dict[str, set[str]] = {}
        for group in get("similar_handshapes", DEFAULT_SIMILAR) or []:
            group = normalize(str(group))
            for letter in group:
                self.similar.setdefault(letter, set()).update(set(group) - {letter})

        self.stats: dict[str, TermStats] = {}
        self.letters = ""
        self.suggestions: tuple[Suggestion, ...] = ()
        self.dismissed = False
        self.search_ready = False
        self._context: dict[str, float] = {}  # last context scores, reused while refining
        self.conversation: deque[tuple[float, str]] = deque(maxlen=200)
        self.gloss: tuple[str, ...] = ()  # the utterance so far, as context too
        self.meeting_id = uuid.uuid4().hex[:12] if config.mode == "meet" else ""
        self._heard: dict[str, tuple[str, float]] = {}  # term -> (meeting, when), from captions
        # Metrics for the pitch: accepted suggestions, letters saved, latency.
        self.accepted = 0
        self.letters_saved = 0
        self.last_accept: dict[str, int] | None = None
        self.latency_ms: float | None = None
        self.search_ms: float | None = None
        self.last_search = "letters"
        self._suggesting: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._task: asyncio.Task[None] | None = None

    # ---- lifecycle ----

    async def start(self) -> None:
        if self._task is not None:
            return
        rows = await asyncio.to_thread(self.store.all)
        self.stats = build_stats(rows, self.transcript_weight)
        self.accepted, self.letters_saved = await asyncio.to_thread(self.store.letters_saved)
        sub = self.bus.subscribe(Caption, OutputSent, ModeChanged, UtteranceProgress)
        self._task = asyncio.create_task(self._follow(sub), name="autocomplete")
        self._spawn(self._open_search(rows))

    async def stop(self) -> None:
        tasks = [t for t in [self._task, self._suggesting, *self._tasks] if t is not None]
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._task = self._suggesting = None
        self._tasks.clear()
        if self.search is not None:
            with contextlib.suppress(Exception):
                await self.search.close()

    async def _open_search(self, rows: list[Occurrence]) -> None:
        if self.search is None:
            return
        start = time.monotonic()
        try:
            await self.search.open(rows)
        except Exception as exc:
            log.warning("autocomplete search '%s' unavailable: %s", self.search.name, exc)
            self.bus.publish(
                Notice(
                    "warning",
                    f"Autocomplete: {self.search.name} search isn't available ({exc}); "
                    "suggesting from letters and how often you use each word.",
                )
            )
            return
        self.search_ready = True
        log.info(
            "autocomplete: %s search over %d occurrences ready in %.0f ms",
            self.search.name,
            len(rows),
            (time.monotonic() - start) * 1000,
        )

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _follow(self, sub) -> None:
        try:
            async for event in sub:
                if isinstance(event, Caption):
                    if event.is_final:
                        self._heard_say(event.text)
                elif isinstance(event, OutputSent):
                    self._remember_text(event.text)  # what the signer said is context too
                elif isinstance(event, UtteranceProgress):
                    self.gloss = event.gloss
                elif isinstance(event, ModeChanged):
                    if event.mode == "meet" and not self.meeting_id:
                        self.meeting_id = uuid.uuid4().hex[:12]
                    elif event.mode != "meet":
                        self.meeting_id = ""
        finally:
            sub.close()

    # ---- spelling (called by the utterance buffer, in order with the signs) ----

    @property
    def active(self) -> bool:
        return bool(self.letters)

    def add(self, letter: str) -> None:
        letter = normalize(letter)[:1]
        if not letter or not self.enabled:
            return
        started = time.perf_counter()
        self.letters += letter
        # Right away from what's known (letters, frequency, the last context scores), then
        # refined with a fresh context search.
        self.suggestions = tuple(self.rank(self.letters, self._context))
        self._publish("cached", (time.perf_counter() - started) * 1000)
        if self._suggesting is not None:
            self._suggesting.cancel()
        if len(self.letters) >= self.min_letters:
            self._suggesting = asyncio.create_task(self._refine(self.letters, started))

    def accept(self, index: int = 0) -> SignEvent | None:
        """YES (or a click on an alternate): the suggestion goes into the utterance. With no
        suggestion (or after NO), the letters as spelled do."""
        if not self.letters:
            return None
        if self.dismissed or not self.suggestions:
            return self.finish()
        choice = self.suggestions[min(max(index, 0), len(self.suggestions) - 1)]
        spelled = len(self.letters)
        saved = max(0, len(normalize(choice.term)) - spelled)
        self.accepted += 1
        self.letters_saved += saved
        self.last_accept = {"spelled": spelled, "length": len(normalize(choice.term))}
        log.info("autocomplete: accepted after %d of %d letters", spelled, spelled + saved)
        self._record(choice.term, choice.kind, letters_spelled=spelled)
        return self._done(choice.term)

    def finish(self) -> SignEvent | None:
        """Keep the letters as spelled (a new word, or the signer moved on)."""
        if not self.letters:
            return None
        letters = self.letters
        known = self.stats.get(letters)
        if known is not None:
            term, kind = known.term, known.kind
        elif is_common(letters):
            term, kind = letters.lower(), "term"
        elif len(letters) <= 3:
            term, kind = letters, "acronym"
        else:
            term, kind = letters.capitalize(), "name"
        if len(letters) >= self.min_letters:
            self._record(term, kind, letters_spelled=None)
        return self._done(term)

    def dismiss(self) -> None:
        """NO: hide the suggestions for this word; NO again drops the letters."""
        if not self.letters:
            return
        if self.dismissed:
            self.clear()
            return
        self.dismissed = True
        self._publish(self.last_search)

    def clear(self) -> None:
        self._reset()
        self._publish("letters")

    def _done(self, term: str) -> SignEvent:
        self._reset()
        self._publish("letters")
        return make_sign_event(term, 1.0, "fingerspell")

    def _reset(self) -> None:
        if self._suggesting is not None:
            self._suggesting.cancel()
            self._suggesting = None
        self.letters, self.suggestions, self.dismissed = "", (), False

    def _publish(self, search: str, latency_ms: float | None = None) -> None:
        shown = () if self.dismissed or len(self.letters) < self.min_letters else self.suggestions
        self.bus.publish(
            AutocompleteUpdate(self.letters, shown, self.dismissed, search, latency_ms)
        )

    async def _refine(self, letters: str, started: float) -> None:
        context: dict[str, float] | None = None
        search = "letters"
        text = self.context_text()
        candidates = self.candidates(letters)
        if self.search_ready and self.search is not None and text and candidates:
            field = "prefix3" if len(letters) >= 3 else "prefix2"
            prefixes = sorted({c[: 3 if field == "prefix3" else 2] for c in candidates})
            t0 = time.perf_counter()
            try:
                context = await asyncio.wait_for(
                    self.search.context(text, field, prefixes), self.search_timeout
                )
                search = self.search.name
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # slow or failed: rank without context this time
                log.warning("autocomplete search failed (%s); letters only", type(exc).__name__)
            self.search_ms = (time.perf_counter() - t0) * 1000
        if letters != self.letters:
            return  # the signer kept spelling (or accepted) meanwhile
        if context is not None:
            self._context = context
        self.suggestions = tuple(self.rank(letters, context))
        self.latency_ms = (time.perf_counter() - started) * 1000
        self.last_search = search
        log.info(
            "autocomplete: %d letters, %d candidates, %s search %s ms, total %.1f ms",
            len(letters),
            len(candidates),
            search,
            f"{self.search_ms:.1f}" if self.search_ms is not None and context is not None else "-",
            self.latency_ms,
        )
        self._publish(search, self.latency_ms)

    # ---- ranking ----

    def letter_match(self, letters: str, term_norm: str) -> float | None:
        """1.0 for an exact prefix, less for each look-alike handshape; None if no match."""
        if len(term_norm) < len(letters):
            return None
        swaps = 0
        for spelled, actual in zip(letters, term_norm, strict=False):
            if spelled != actual:
                if actual not in self.similar.get(spelled, ()):
                    return None
                swaps += 1
                if swaps > self.max_substitutions:
                    return None
        return max(0.0, 1.0 - swaps * self.substitution_penalty)

    def candidates(self, letters: str) -> list[str]:
        """Remembered words the letters could be the start of, look-alike swaps included.
        Their first 2 or 3 letters are the search filter (Moss has no prefix operator)."""
        if len(letters) < self.min_letters:
            return []
        return [t for t in self.stats if self.letter_match(letters, t) is not None]

    def rank(self, letters: str, context: dict[str, float] | None = None) -> list[Suggestion]:
        found = [(t, m) for t in self.stats if (m := self.letter_match(letters, t)) is not None]
        if not found or len(letters) < self.min_letters:
            return []
        now = time.time()
        w = self.weights
        most = max(self.stats[t].count for t, _ in found)
        ctx = {t: (context or {}).get(t, 0.0) for t, _ in found}
        low = min(ctx.values())
        spread = max(max(ctx.values()) - low, self.context_spread)
        scored = []
        for term_norm, match in found:
            st = self.stats[term_norm]
            frequency = math.log1p(st.count) / math.log1p(most) if most > 0 else 0.0
            age_days = max(0.0, now - st.last_used) / 86400
            recency = 0.5 ** (age_days / self.half_life_days) if st.last_used else 0.0
            score = (
                w["letters"] * match
                + w["context"] * (ctx[term_norm] - low) / spread
                + w["frequency"] * frequency
                + w["recency"] * recency
            )
            scored.append(Suggestion(st.term, st.kind, round(score, 4)))
        scored.sort(key=lambda s: (-s.score, s.term))
        return scored[: 1 + self.alternates]

    # ---- conversation (in memory only) ----

    def _remember_text(self, text: str) -> None:
        now = time.monotonic()
        self.conversation.append((now, text))
        while self.conversation and now - self.conversation[0][0] > self.context_seconds:
            self.conversation.popleft()

    def context_text(self) -> str:
        now = time.monotonic()
        recent = [t for when, t in self.conversation if now - when <= self.context_seconds]
        signs = [g.lower() for g in self.gloss if g.isalpha()]  # TENNIS, not fs- words or tags
        return " ".join([*recent, *signs]).strip()

    def _heard_say(self, text: str) -> None:
        self._remember_text(text)
        if not self.learn_from_captions:
            return
        now = time.time()
        fresh = []
        for term, kind in extract_terms(text):
            key = normalize(term)
            if len(key) < self.min_letters:
                continue
            meeting, when = self._heard.get(key, ("", 0.0))
            if meeting == self.meeting_id and now - when < self.transcript_repeat_seconds:
                continue  # the same word again in the same stretch of the meeting
            self._heard[key] = (self.meeting_id, now)
            fresh.append((term, kind))
        if fresh:
            occurrences = [self._occurrence(t, k, "transcript") for t, k in fresh]
            self._store(occurrences, self.context_text())

    # ---- recording ----

    def _occurrence(self, term: str, kind: str, source: str, spelled: int | None = None):
        return Occurrence(
            term=term,
            kind=kind,
            source=source,
            meeting_id=self.meeting_id,
            letters_spelled=spelled,
        )

    def _record(self, term: str, kind: str, letters_spelled: int | None) -> None:
        occ = self._occurrence(term, kind, "fingerspelled", letters_spelled)
        self._store([occ], self.context_text())

    def _store(self, occurrences: list[Occurrence], context: str) -> None:
        for occ in occurrences:  # counted right away; written and tagged in the background
            entry = self.stats.setdefault(occ.term_norm, TermStats(occ.term, occ.kind))
            entry.add(occ, self.transcript_weight)
        self._spawn(self._save(occurrences, context))

    async def _save(self, occurrences: list[Occurrence], context: str) -> None:
        await asyncio.to_thread(self.store.add, occurrences)
        await self._index(occurrences)
        try:  # the conversation goes to the tagger, and only the tags are kept
            tagged = await self.tagger.tag([o.term for o in occurrences], context)
        except Exception as exc:
            log.warning("autocomplete tags failed (%s); keeping the words untagged", exc)
            return
        updated = []
        for occ in occurrences:
            result: Tagged | None = tagged.get(occ.term)
            if result is None or not (result.tags or result.kind):
                continue
            new = with_tags(occ, result.tags, result.kind)
            updated.append(new)
            await asyncio.to_thread(self.store.set_tags, occ.id, new.tags, new.kind)
            entry = self.stats.get(occ.term_norm)
            if entry is not None and entry.ids and entry.ids[-1] == occ.id:
                entry.tags = new.tags
                if occ.source == "transcript" or result.kind:
                    entry.kind = new.kind
                if result.display and normalize(result.display) == occ.term_norm:
                    entry.term = result.display
        await self._index(updated)

    async def _index(self, occurrences: list[Occurrence]) -> None:
        if occurrences and self.search_ready and self.search is not None:
            try:
                await self.search.add(occurrences)
            except Exception as exc:
                log.warning("autocomplete: couldn't index words (%s)", type(exc).__name__)

    # ---- the memory, for Settings ----

    async def words(self) -> list[dict[str, Any]]:
        rows = await asyncio.to_thread(self.store.all)
        by_term: dict[str, list[Occurrence]] = {}
        for occ in rows:
            by_term.setdefault(occ.term_norm, []).append(occ)
        out = []
        for term_norm, occs in by_term.items():
            st = self.stats.get(term_norm) or build_stats(occs)[term_norm]
            out.append(
                {
                    "term": st.term,
                    "term_norm": term_norm,
                    "kind": st.kind,
                    "count": len(occs),
                    "last_used": max(o.used_at for o in occs),
                    "tags": list(st.tags),
                    "occurrences": [
                        {"id": o.id, "source": o.source, "used_at": o.used_at, "tags": list(o.tags)}
                        for o in sorted(occs, key=lambda o: -o.used_at)
                    ],
                }
            )
        out.sort(key=lambda w: -w["last_used"])
        return out

    async def delete_word(self, term: str) -> int:
        term_norm = normalize(term)
        ids = await asyncio.to_thread(self.store.delete_term, term_norm)
        self.stats.pop(term_norm, None)
        self._context.pop(term_norm, None)
        await self._unindex(ids)
        self._refresh_suggestions()
        return len(ids)

    async def delete_occurrence(self, occ_id: str) -> bool:
        occ = await asyncio.to_thread(self.store.get, occ_id)
        if occ is None:
            return False
        await asyncio.to_thread(self.store.delete, [occ_id])
        rest = await asyncio.to_thread(self.store.for_term, occ.term_norm)
        if rest:
            self.stats[occ.term_norm] = build_stats(rest, self.transcript_weight)[occ.term_norm]
        else:
            self.stats.pop(occ.term_norm, None)
            self._context.pop(occ.term_norm, None)
        await self._unindex([occ_id])
        self._refresh_suggestions()
        return True

    async def _unindex(self, ids: list[str]) -> None:
        if ids and self.search is not None and self.search_ready:
            await self.search.delete(ids)

    def _refresh_suggestions(self) -> None:
        if self.letters:
            self.suggestions = tuple(self.rank(self.letters, self._context))
            self._publish(self.last_search)

    def metrics(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "letters_saved": self.letters_saved,
            "last_accept": self.last_accept,
            "latency_ms": None if self.latency_ms is None else round(self.latency_ms, 1),
            "search_ms": None if self.search_ms is None else round(self.search_ms, 1),
            "search": (self.search.name if self.search_ready and self.search else "letters"),
            "words": len(self.stats),
        }
