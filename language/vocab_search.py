"""Context search over the word memory: which remembered words fit the conversation?

`vocab_search: moss` (config.demo.yaml) builds a Moss session index on the Mac at startup
from the SQLite rows (language/vocab.py) and queries it in memory. The session is never
pushed: Moss's persistent indexes live in Moss's cloud, so the memory stays in our local
file and the Moss session is rebuilt from it each time the engine starts. Opening a
session checks the project keys (MOSS_PROJECT_ID, MOSS_PROJECT_KEY in .env) and may fetch
the embedding model, so it needs the network once at startup; queries don't.

`vocab_search: mock` (the default) scores word overlap between the conversation and each
word's tags. No keys, no network; good enough for tests and `make mock`.

Either way, search only says how well each word fits the conversation. Letters, frequency
and recency are scored in language/autocomplete.py, which also falls back to ranking
without context if search fails or is slow.
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from language.vocab import Occurrence
from shared.config import Config

log = logging.getLogger(__name__)

STOPWORDS = frozenset(
    """a about after again all also am an and any are as at be been but by can could did do
    does doing for from get got had has have he her here him his how i if in into is it its
    just let like me my no not now of on one or our out over please really so some than that
    the their them then there these they this those to too up us very was we well were what
    when where which who why will with would yeah yes you your okay ok hi hey thanks thank
    great good going gonna want""".split()
)


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS}


class VocabSearch(ABC):
    name = "search"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.top_k = int(config.get("autocomplete.top_k", 50))

    @abstractmethod
    async def open(self, occurrences: Sequence[Occurrence]) -> None:
        """Index every stored occurrence. Raises if this search can't run."""

    @abstractmethod
    async def add(self, occurrences: Sequence[Occurrence]) -> None:
        """Add or replace documents (same id = replace, e.g. once tags arrive)."""

    @abstractmethod
    async def delete(self, ids: Sequence[str]) -> None: ...

    @abstractmethod
    async def context(self, text: str, field: str, prefixes: Sequence[str]) -> dict[str, float]:
        """How well each word fits `text`, for docs whose `field` (prefix2 or prefix3) is in
        `prefixes`: {term_norm: score}, best occurrence per word. Missing = no match."""

    async def close(self) -> None:  # noqa: B027 (optional: only Moss holds resources)
        return None


class KeywordSearch(VocabSearch):
    """The mock: shared words between the conversation and a word's text (word + tags)."""

    name = "keyword"

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.docs: dict[str, Occurrence] = {}

    async def open(self, occurrences: Sequence[Occurrence]) -> None:
        self.docs = {o.id: o for o in occurrences}

    async def add(self, occurrences: Sequence[Occurrence]) -> None:
        self.docs.update({o.id: o for o in occurrences})

    async def delete(self, ids: Sequence[str]) -> None:
        for i in ids:
            self.docs.pop(i, None)

    async def context(self, text: str, field: str, prefixes: Sequence[str]) -> dict[str, float]:
        query = words(text)
        wanted = set(prefixes)
        scores: dict[str, float] = {}
        for occ in self.docs.values():
            if occ.metadata()[field] not in wanted:
                continue
            doc = words(" ".join(occ.tags))
            if not doc or not query:
                continue
            score = len(query & doc) / len(doc)
            if score > scores.get(occ.term_norm, 0.0):
                scores[occ.term_norm] = score
        return scores


class MossSearch(VocabSearch):
    """A Moss session index, built in memory from the local rows and never pushed."""

    name = "moss"

    def __init__(self, config: Config, client: Any = None) -> None:
        super().__init__(config)
        self.index_name = str(config.get("autocomplete.moss_index", "signbridge-vocab"))
        self.model_id = str(config.get("autocomplete.moss_model", "moss-minilm"))
        self.alpha = float(config.get("autocomplete.moss_alpha", 0.6))
        self._client = client
        self.session: Any = None
        self.load_seconds: float | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            from moss import MossClient

            project_id = Config.secret("MOSS_PROJECT_ID")
            project_key = Config.secret("MOSS_PROJECT_KEY")
            if not project_id or not project_key:
                raise RuntimeError("MOSS_PROJECT_ID / MOSS_PROJECT_KEY aren't set (.env)")
            self._client = MossClient(project_id, project_key)
        return self._client

    async def open(self, occurrences: Sequence[Occurrence]) -> None:
        start = time.monotonic()
        # auto_load_on_init=False: start empty, never download a cloud index. Our SQLite
        # file is the memory; this session is only the search over it.
        self.session = await self.client.session(
            self.index_name, self.model_id, auto_load_on_init=False
        )
        if occurrences:
            await self.add(occurrences)
        self.load_seconds = time.monotonic() - start
        log.info(
            "Moss session ready: %d occurrences in %.0f ms",
            len(occurrences),
            self.load_seconds * 1000,
        )

    async def add(self, occurrences: Sequence[Occurrence]) -> None:
        from moss import DocumentInfo

        docs = [DocumentInfo(id=o.id, text=o.text(), metadata=o.metadata()) for o in occurrences]
        if docs:
            await self.session.add_docs(docs)

    async def delete(self, ids: Sequence[str]) -> None:
        if ids:
            await self.session.delete_docs(list(ids))

    async def context(self, text: str, field: str, prefixes: Sequence[str]) -> dict[str, float]:
        from moss import QueryOptions

        if not text.strip() or not prefixes:
            return {}
        options = QueryOptions(
            top_k=self.top_k,
            alpha=self.alpha,
            filter={"field": field, "condition": {"$in": list(prefixes)}},
        )
        result = await self.session.query(text, options)
        scores: dict[str, float] = {}
        for doc in result.docs:
            term = (doc.metadata or {}).get("term_norm", "")
            if term and float(doc.score) > scores.get(term, 0.0):
                scores[term] = float(doc.score)
        return scores

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None
        if self._client is not None:
            await self._client.close()
