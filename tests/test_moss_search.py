"""The Moss search: a session index built on the Mac from the local rows, never pushed.
A fake Moss client checks how the SDK is called; the live tests use the real one
(MOSS_PROJECT_ID / MOSS_PROJECT_KEY in .env, `uv run pytest --live`)."""

import time
from types import SimpleNamespace

import pytest

from language.autocomplete import Autocompleter
from language.tagger import MockTagger
from language.vocab import Occurrence, VocabStore
from language.vocab_search import MossSearch
from shared.bus import Bus
from shared.config import Config, load_config
from tests.test_autocomplete import seed, spell, until


class FakeSession:
    def __init__(self):
        self.docs = {}
        self.queries = []

    async def add_docs(self, docs):
        added = sum(d.id not in self.docs for d in docs)
        self.docs.update({d.id: d for d in docs})
        return added, len(docs) - added

    async def delete_docs(self, ids):
        return sum(self.docs.pop(i, None) is not None for i in ids)

    async def query(self, text, options):
        self.queries.append((text, options))
        field, wanted = options.filter["field"], set(options.filter["condition"]["$in"])
        hits = [
            SimpleNamespace(id=d.id, metadata=d.metadata, score=0.9 if "tennis" in d.text else 0.2)
            for d in self.docs.values()
            if d.metadata[field] in wanted
        ]
        return SimpleNamespace(docs=hits[: options.top_k])

    async def push_index(self):
        raise AssertionError("the vocabulary must never be pushed to Moss's cloud")

    async def close(self):
        self.closed = True


class FakeClient:
    def __init__(self):
        self.session_args = None
        self.sessions = []

    async def session(self, index_name, model_id=None, *, auto_load_on_init=True):
        self.session_args = (index_name, model_id, auto_load_on_init)
        self.sessions.append(FakeSession())
        return self.sessions[-1]

    async def close(self):
        pass


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
    assert scores == {"JULIAN": 0.9, "JUPYTER": 0.2}
    text, options = client.sessions[0].queries[0]
    assert options.filter == {"field": "prefix2", "condition": {"$in": ["JU"]}}
    assert options.alpha == pytest.approx(0.6)


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


async def test_missing_keys_mean_no_moss(config, monkeypatch):
    monkeypatch.delenv("MOSS_PROJECT_ID", raising=False)
    monkeypatch.delenv("MOSS_PROJECT_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MOSS_PROJECT_ID"):
        await MossSearch(config).open([])


needs_moss = pytest.mark.skipif(
    not (Config.secret("MOSS_PROJECT_ID") and Config.secret("MOSS_PROJECT_KEY")),
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
