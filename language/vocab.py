"""The signer's word memory for fingerspelling autocomplete: one row per occurrence.

The source of truth is a SQLite file on the Mac (~/Library/Application Support/
calhacks-2026/vocab.sqlite). Each row is one time a word was used: fingerspelled by the
signer, or heard in a call's captions. Only the word, a few topic tags and metadata are
kept; never the sentence, caption or transcript it came from.

At startup every row is added to the search index (language/vocab_search.py) as one
document; frequency and last use come from these rows, not from the index.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

from shared.config import SUPPORT, Config

KINDS = ("name", "acronym", "term")
SOURCES = ("fingerspelled", "transcript")

SCHEMA = """
CREATE TABLE IF NOT EXISTS occurrences (
    id TEXT PRIMARY KEY,
    term TEXT NOT NULL,
    term_norm TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    used_at REAL NOT NULL,
    meeting_id TEXT NOT NULL DEFAULT '',
    prefix2 TEXT NOT NULL,
    prefix3 TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    letters_spelled INTEGER
);
CREATE INDEX IF NOT EXISTS occurrences_term ON occurrences (term_norm);
"""


def vocab_path(config: Config) -> Path:
    """Where the memory lives: autocomplete.db_path, or Application Support. The mock search
    (`make mock`, tests) keeps its own file, so mock demos never mix into the real memory.
    CALHACKS_VOCAB_DB overrides both (the tests point it at a temporary folder)."""
    if os.environ.get("CALHACKS_VOCAB_DB"):
        return Path(os.environ["CALHACKS_VOCAB_DB"])
    if config.get("autocomplete.db_path"):
        return config.path("autocomplete.db_path")
    name = "vocab.sqlite" if config.vocab_search != "mock" else "vocab-mock.sqlite"
    return SUPPORT / name


def normalize(word: str) -> str:
    """Uppercase letters only: "Jupyter's" -> "JUPYTERS", "k8s" -> "KS"."""
    return re.sub(r"[^A-Z]", "", word.upper())


@dataclass(frozen=True)
class Occurrence:
    term: str  # display form: "Julian", "API", "Kubernetes"
    kind: str
    source: str
    used_at: float = field(default_factory=time.time)
    meeting_id: str = ""
    tags: tuple[str, ...] = ()
    # Fingerspelled and accepted: how many letters were spelled (for "letters saved").
    letters_spelled: int | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def term_norm(self) -> str:
        return normalize(self.term)

    @property
    def prefix2(self) -> str:
        return self.term_norm[:2]

    @property
    def prefix3(self) -> str:
        return self.term_norm[:3]

    def text(self) -> str:
        """The search document's text: the word and its topic tags."""
        return f"{self.term} — {', '.join(self.tags)}" if self.tags else self.term

    def metadata(self) -> dict[str, str]:
        """The search document's metadata (Moss metadata values are all strings)."""
        return {
            "term": self.term,
            "term_norm": self.term_norm,
            "kind": self.kind,
            "source": self.source,
            "used_at": f"{self.used_at:.3f}",
            "meeting_id": self.meeting_id,
            "prefix2": self.prefix2,
            "prefix3": self.prefix3,
        }


@dataclass
class TermStats:
    """Everything ranking needs about one word, kept in memory (loaded from the rows)."""

    term: str
    kind: str
    count: float = 0.0  # weighted: words heard in captions count less than ones you spelled
    last_used: float = 0.0
    tags: tuple[str, ...] = ()
    ids: list[str] = field(default_factory=list)

    def add(self, occ: Occurrence, transcript_weight: float) -> None:
        self.count += transcript_weight if occ.source == "transcript" else 1.0
        if occ.used_at >= self.last_used:
            self.last_used = occ.used_at
            if occ.tags:
                self.tags = occ.tags
        if occ.source == "fingerspelled":
            self.term, self.kind = occ.term, occ.kind  # how the signer spells it wins
        self.ids.append(occ.id)


def build_stats(
    occurrences: Iterable[Occurrence], transcript_weight: float = 0.5
) -> dict[str, TermStats]:
    stats: dict[str, TermStats] = {}
    for occ in sorted(occurrences, key=lambda o: o.used_at):
        entry = stats.setdefault(occ.term_norm, TermStats(occ.term, occ.kind))
        entry.add(occ, transcript_weight)
    return stats


class VocabStore:
    """The SQLite file. Small and local, so calls are quick; the engine still runs them off
    the event loop (asyncio.to_thread).

    Every call holds `lock`, because the engine's background writes (a word is recorded, then
    tagged) run in worker threads that outlive the task that started them: cancelling that
    task doesn't stop a thread already inside asyncio.to_thread. The lock also makes close()
    wait for an in-flight write instead of closing the connection under it, and calls after
    close do nothing rather than crash the process."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.lock = threading.RLock()
        self.closed = False
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.db.close()

    def add(self, occurrences: Iterable[Occurrence]) -> None:
        rows = [
            (
                o.id,
                o.term,
                o.term_norm,
                o.kind,
                o.source,
                o.used_at,
                o.meeting_id,
                o.prefix2,
                o.prefix3,
                ",".join(o.tags),
                o.letters_spelled,
            )
            for o in occurrences
        ]
        with self.lock:
            if self.closed:
                return
            with self.db:
                self.db.executemany(
                    "INSERT OR REPLACE INTO occurrences VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
                )

    def set_tags(self, occ_id: str, tags: tuple[str, ...], kind: str | None = None) -> None:
        with self.lock:
            if self.closed:
                return
            with self.db:
                tag_text = ",".join(tags)
                self.db.execute("UPDATE occurrences SET tags = ? WHERE id = ?", (tag_text, occ_id))
                if kind in KINDS:
                    self.db.execute("UPDATE occurrences SET kind = ? WHERE id = ?", (kind, occ_id))

    def all(self) -> list[Occurrence]:
        return self._select("", ())

    def for_term(self, term_norm: str) -> list[Occurrence]:
        return self._select("WHERE term_norm = ?", (term_norm,))

    def get(self, occ_id: str) -> Occurrence | None:
        found = self._select("WHERE id = ?", (occ_id,))
        return found[0] if found else None

    def delete_term(self, term_norm: str) -> list[str]:
        """Delete every occurrence of a word. Returns the deleted ids."""
        with self.lock:
            ids = [o.id for o in self.for_term(term_norm)]
            if self.closed:
                return ids
            with self.db:
                self.db.execute("DELETE FROM occurrences WHERE term_norm = ?", (term_norm,))
            return ids

    def delete(self, ids: Iterable[str]) -> None:
        with self.lock:
            if self.closed:
                return
            with self.db:
                self.db.executemany("DELETE FROM occurrences WHERE id = ?", [(i,) for i in ids])

    def letters_saved(self) -> tuple[int, int]:
        """(accepted suggestions, letters saved) over every accepted fingerspelled word."""
        with self.lock:
            if self.closed:
                return (0, 0)
            row = self.db.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(term_norm) - letters_spelled), 0) "
                "FROM occurrences WHERE letters_spelled IS NOT NULL"
            ).fetchone()
        return int(row[0]), int(row[1])

    def _select(self, where: str, args: tuple) -> list[Occurrence]:
        with self.lock:
            if self.closed:
                return []
            cursor = self.db.execute(
                "SELECT id, term, kind, source, used_at, meeting_id, tags, letters_spelled "
                f"FROM occurrences {where} ORDER BY used_at",
                args,
            )
            rows = cursor.fetchall()
        return [
            Occurrence(
                id=row[0],
                term=row[1],
                kind=row[2],
                source=row[3],
                used_at=float(row[4]),
                meeting_id=row[5],
                tags=tuple(t for t in row[6].split(",") if t),
                letters_spelled=row[7],
            )
            for row in rows
        ]


def with_tags(occ: Occurrence, tags: Iterable[str], kind: str | None = None) -> Occurrence:
    return replace(occ, tags=tuple(tags), kind=kind if kind in KINDS else occ.kind)
