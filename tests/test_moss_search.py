"""The Moss search: a session index built on the Mac from the local rows, never pushed.
A fake Moss client checks how the SDK is called; the live tests use the real one
(MOSS_PROJECT_ID / MOSS_PROJECT_KEY in .env, `uv run pytest --live`)."""

import time

import pytest
from moss import QueryResultDocumentInfo, SearchResult

from language.autocomplete import Autocompleter
from language.tagger import MockTagger
from language.vocab import Occurrence, VocabStore
from language.vocab_search import MossSearch
from shared.bus import Bus
from shared.config import Config, load_config
from tests.test_autocomplete import seed, spell, until

# The fakes mirror moss 1.21's SessionIndex and MossClient: the same signatures and
# defaults, and the real result types, so what passes here is what the SDK accepts.
# MossSearch builds real DocumentInfo and QueryOptions objects either way.
DEFAULT_TOP_K = 5  # SessionIndex.query's default when options.top_k is None
DEFAULT_ALPHA = 0.8


class FakeSession:
    def __init__(self, name="signbridge-vocab", model_id="moss-minilm"):
        self.name = name
        self.model_id = model_id
        self.docs = {}
        self.queries = []
        self.closed = False

    @property
    def doc_count(self):
        return len(self.docs)

    async def add_docs(self, docs, options=None, *, chunker=None, chunking=None):
        docs = list(docs)
        added = sum(d.id not in self.docs for d in docs)
        self.docs.update({d.id: d for d in docs})  # same id replaces: upsert is on by default
        return added, len(docs) - added

    async def delete_docs(self, doc_ids):
        return sum(self.docs.pop(i, None) is not None for i in doc_ids)

    async def query(self, query, options=None):
        self.queries.append((query, options))
        top_k = getattr(options, "top_k", None) or DEFAULT_TOP_K
        alpha = getattr(options, "alpha", None)
        alpha = DEFAULT_ALPHA if alpha is None else alpha
        condition = (getattr(options, "filter", None) or {}).get("condition") or {}
        field = (getattr(options, "filter", None) or {}).get("field")
        wanted = set(condition.get("$in", ()))
        if not query.strip():
            return SearchResult(docs=[], query=query, index_name=self.name)  # no embedding
        hits = [
            QueryResultDocumentInfo(
                id=d.id,
                text=d.text,
                metadata=d.metadata,
                # The real score is vector similarity alone, so alpha never changes it.
                score=0.9 if "tennis" in d.text else 0.2,
            )
            for d in self.docs.values()
            if field is None or (d.metadata or {}).get(field) in wanted
        ]
        hits.sort(key=lambda d: -d.score)
        return SearchResult(
            docs=hits[:top_k],
            query=query,
            index_name=self.name,
            time_taken_ms=1,
            model_id=self.model_id,
        )

    async def get_docs(self, options=None):
        return list(self.docs.values())

    async def push_index(self):
        raise AssertionError("the vocabulary must never be pushed to Moss's cloud")

    async def close(self):
        self.closed = True


class FakeClient:
    DEFAULT_MODEL_ID = "moss-minilm"

    def __init__(self, project_id="test-project", project_key="test-key", *, cache_path=None):
        self.session_args = None
        self.sessions = []
        self.closed = False

    async def session(
        self,
        index_name,
        model_id=None,
        *,
        artifact_version=None,
        manifest_sha256=None,
        auto_load_on_init=True,
    ):
        self.session_args = (index_name, model_id, auto_load_on_init)
        self.sessions.append(FakeSession(index_name, model_id or self.DEFAULT_MODEL_ID))
        return self.sessions[-1]

    async def close(self):
        self.closed = True


@pytest.fixture
def config():
    return load_config().all_mocks()


async def test_session_starts_empty_and_is_built_from_the_local_rows(config):
    client = FakeClient()
    search = MossSearch(config, client=client)
    occs = [Occurrence("Julian", "name", "fingerspelled", tags=("tennis",))]
    await search.open(occs)
    assert client.session_args == ("signbridge-vocab", "moss-minilm", False)  # no cloud load
    (doc,) = client.sessions[0].docs.values()
    assert doc.text == "Julian — tennis"
    assert doc.metadata["term_norm"] == "JULIAN" and doc.metadata["prefix3"] == "JUL"
    assert all(isinstance(v, str) for v in doc.metadata.values())  # Moss metadata: strings
    assert float(doc.metadata["used_at"]) == pytest.approx(occs[0].used_at, abs=0.001)


async def test_query_filters_on_the_prefix_and_returns_the_best_score_per_word(config):
    client = FakeClient()
    search = MossSearch(config, client=client)
    await search.open(
        [
            Occurrence("Julian", "name", "fingerspelled", tags=("tennis",)),
            Occurrence("Julian", "name", "fingerspelled", tags=("work",)),
            Occurrence("Jupyter", "term", "fingerspelled", tags=("data",)),
            Occurrence("Kim", "name", "fingerspelled"),
        ]
    )
    scores = await search.context("tennis on Saturday", "prefix2", ["JU"])
    assert scores == pytest.approx({"JULIAN": 0.9, "JUPYTER": 0.2}, abs=1e-6)
    text, options = client.sessions[0].queries[0]
    assert options.filter == {"field": "prefix2", "condition": {"$in": ["JU"]}}
    assert options.alpha == pytest.approx(0.6)
    assert options.top_k == 50  # the real default is 5, far too few for our candidates


async def test_autocomplete_with_moss_adds_new_words_and_deletes_them(config):
    client = FakeClient()
    store = VocabStore(":memory:")
    seed(store)
    ac = Autocompleter(Bus(), config, store, MossSearch(config, client=client), MockTagger())
    await ac.start()
    await until(lambda: ac.search_ready)
    session = client.sessions[0]
    assert len(session.docs) == 6
    ac._remember_text("tennis this weekend")
    assert (await spell(ac, "JU"))[0] == "Julian"
    assert ac.metrics()["search"] == "moss"
    ac.accept()
    await until(lambda: len(session.docs) == 7)
    await ac.delete_word("Julian")
    assert all(d.metadata["term"] != "Julian" for d in session.docs.values())
    await ac.stop()


def test_the_vocabulary_is_never_pushed_to_the_cloud():
    """A record of the names a Deaf person spells stays on their machine: the session index
    is built from the local rows and only ever queried in memory."""
    import inspect

    from language import vocab_search

    source = inspect.getsource(vocab_search)
    for cloud in ("push_index", "create_index", "load_index", "save_to_disk"):
        assert cloud not in source, f"{cloud} would write the vocabulary to Moss's cloud"


async def test_missing_keys_mean_no_moss(config, monkeypatch):
    monkeypatch.delenv("MOSS_PROJECT_ID", raising=False)
    monkeypatch.delenv("MOSS_PROJECT_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MOSS_PROJECT_ID"):
        await MossSearch(config).open([])


def _moss_keys() -> bool:
    load_config()  # reads .env into the environment, which Config.secret looks at
    return bool(Config.secret("MOSS_PROJECT_ID") and Config.secret("MOSS_PROJECT_KEY"))


needs_moss = pytest.mark.skipif(
    not _moss_keys(),
    reason="MOSS_PROJECT_ID / MOSS_PROJECT_KEY aren't set",
)


def synthetic(n: int) -> list[Occurrence]:
    topics = [
        ("tennis", "doubles"),
        ("data analysis", "notebooks"),
        ("cooking", "recipes"),
        ("kubernetes", "deploys"),
        ("budget", "finance"),
    ]
    names = ["Avery", "Bao", "Chidi", "Dana", "Esme", "Farid", "Gita", "Hiro", "Ines", "Jules"]
    now = time.time()
    return [
        Occurrence(
            f"{names[i % len(names)]}{i // len(names)}",
            "name",
            "fingerspelled",
            used_at=now - i * 3600,
            tags=topics[i % len(topics)],
        )
        for i in range(n)
    ]


@pytest.mark.live
@needs_moss
async def test_live_moss_ranks_by_conversation(config):
    store = VocabStore(":memory:")
    seed(store)
    ac = Autocompleter(Bus(), config, store, MossSearch(config), MockTagger())
    await ac.start()
    await until(lambda: not ac._tasks, seconds=60)
    assert ac.search_ready
    ac._remember_text("We played a long tennis match this weekend, doubles again.")
    assert (await spell(ac, "JU"))[0] == "Julian"
    ac.clear()
    ac.conversation.clear()
    ac._remember_text("The data analysis notebook keeps crashing when I plot the survey.")
    assert (await spell(ac, "JU"))[0] == "Jupyter"
    print(f"\nMoss query {ac.search_ms:.1f} ms, letter to suggestion {ac.latency_ms:.1f} ms")
    assert ac.latency_ms < 50
    await ac.stop()


@pytest.mark.live
@needs_moss
async def test_live_moss_startup_load_of_500_occurrences(config):
    search = MossSearch(config)
    occs = synthetic(500)
    start = time.monotonic()
    await search.open(occs)
    seconds = time.monotonic() - start
    print(f"\nMoss session with {len(occs)} occurrences ready in {seconds * 1000:.0f} ms")
    assert search.session.doc_count == 500
    await search.close()
