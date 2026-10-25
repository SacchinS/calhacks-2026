"""Fingerspelling autocomplete: ranking, learning, the fallback, deleting, and the flow into
the utterance. Uses the keyword search (the mock); Moss itself is in test_moss_search.py."""

import asyncio
import time

import pytest

from language.autocomplete import Autocompleter
from language.tagger import MockTagger, Tagged
from language.utterance import UtteranceBuffer
from language.vocab import Occurrence, VocabStore
from language.vocab_search import KeywordSearch, VocabSearch
from shared.bus import Bus
from shared.config import load_config
from shared.events import AutocompleteUpdate, Caption, Letter, Notice, SignEvent

DAY = 86400


def seed(store: VocabStore) -> None:
    now = time.time()
    store.add(
        [
            # Julian: spelled once, three weeks ago, while talking about tennis.
            Occurrence(
                "Julian",
                "name",
                "fingerspelled",
                used_at=now - 21 * DAY,
                tags=("tennis", "doubles partner", "weekend"),
            ),
            # Jupyter: used more, and more recently, about data work.
            *[
                Occurrence(
                    "Jupyter",
                    "term",
                    "fingerspelled",
                    used_at=now - d * DAY,
                    tags=("notebooks", "data analysis", "python"),
                )
                for d in (2, 3, 5)
            ],
            *[
                Occurrence(
                    "June",
                    "name",
                    "fingerspelled",
                    used_at=now - d * DAY,
                    tags=("calendar", "summer"),
                )
                for d in (10, 12)
            ],
        ]
    )


@pytest.fixture
def config():
    return load_config().all_mocks()


async def make(config, search: VocabSearch | None = None, tagger=None, seeded=True):
    bus = Bus()
    store = VocabStore(":memory:")
    if seeded:
        seed(store)
    ac = Autocompleter(bus, config, store, search or KeywordSearch(config), tagger or MockTagger())
    await ac.start()
    for _ in range(100):
        if ac.search_ready or not ac._tasks:
            break
        await asyncio.sleep(0.01)
    return ac


async def spell(ac: Autocompleter, letters: str) -> list[str]:
    for letter in letters:
        ac.add(letter)
    if ac._suggesting is not None:
        await ac._suggesting
    return [s.term for s in ac.suggestions]


async def test_tennis_context_ranks_julian_first(config):
    ac = await make(config)
    ac._remember_text("Did you play tennis this weekend? We need a fourth for doubles.")
    assert (await spell(ac, "JU"))[0] == "Julian"
    await ac.stop()


async def test_data_context_ranks_jupyter_first(config):
    ac = await make(config)
    ac._remember_text("Let's look at the data analysis for the survey in a notebook.")
    assert (await spell(ac, "JU"))[0] == "Jupyter"
    await ac.stop()


async def test_signs_in_the_utterance_count_as_context(config):
    ac = await make(config)
    ac.gloss = ("TENNIS", "PARTNER", "fs-BOB")
    assert (await spell(ac, "JU"))[0] == "Julian"
    await ac.stop()


async def test_without_context_frequency_and_recency_decide(config):
    ac = await make(config)
    assert await spell(ac, "JU") == ["Jupyter", "June", "Julian"]  # top plus 2 alternates
    await ac.stop()


async def test_one_letter_suggests_nothing_yet(config):
    ac = await make(config)
    assert await spell(ac, "J") == []
    await ac.stop()


async def test_a_misread_look_alike_handshape_still_finds_the_word(config):
    ac = await make(config)
    ac._remember_text("tennis doubles this weekend")
    # V for U (look-alike handshapes): still Julian, scored a little lower than exact.
    assert (await spell(ac, "JV"))[0] == "Julian"
    exact = ac.letter_match("JU", "JULIAN")
    assert ac.letter_match("JV", "JULIAN") < exact == 1.0
    assert ac.letter_match("JX", "JULIAN") is None  # X isn't a look-alike for U
    assert ac.letter_match("JVL", "JULIAN") is not None  # one swap allowed
    assert ac.letter_match("JVK", "JULIAN") is None
    await ac.stop()


class BrokenSearch(KeywordSearch):
    name = "broken"

    async def open(self, occurrences):
        raise RuntimeError("no network")


class SlowSearch(KeywordSearch):
    name = "slow"

    async def context(self, text, field, prefixes):
        await asyncio.sleep(1)
        return {}


async def test_falls_back_to_letters_and_frequency_when_search_is_unavailable(config):
    ac = await make(config, BrokenSearch(config))
    notices = ac.bus.subscribe(Notice)
    assert not ac.search_ready
    ac._remember_text("tennis doubles this weekend")  # no search: context can't help
    assert await spell(ac, "JU") == ["Jupyter", "June", "Julian"]
    assert ac.metrics()["search"] == "letters"
    await ac.stop()
    notices.close()


async def test_a_slow_search_doesnt_hold_up_suggestions(config):
    ac = await make(config, SlowSearch(config))
    ac._remember_text("tennis doubles this weekend")
    start = time.perf_counter()
    assert (await spell(ac, "JU"))[0] == "Jupyter"
    assert time.perf_counter() - start < 0.5  # search_timeout_ms is 40
    assert ac.last_search == "letters"
    await ac.stop()


async def test_latency_is_measured(config):
    ac = await make(config)
    ac._remember_text("tennis")
    await spell(ac, "JU")
    metrics = ac.metrics()
    assert metrics["search"] == "keyword"
    assert 0 <= metrics["latency_ms"] < 50
    await ac.stop()


async def test_deleting_a_word_removes_it_from_suggestions_and_the_file(config):
    ac = await make(config)
    assert "Julian" in await spell(ac, "JU")
    ac.clear()
    assert await ac.delete_word("Julian") == 1
    assert "Julian" not in await spell(ac, "JU")
    assert ac.store.for_term("JULIAN") == []
    assert all(o.term != "Julian" for o in ac.search.docs.values())
    await ac.stop()


async def test_deleting_one_occurrence_lowers_the_count(config):
    ac = await make(config)
    (word,) = [w for w in await ac.words() if w["term"] == "Jupyter"]
    assert word["count"] == 3
    assert await ac.delete_occurrence(word["occurrences"][0]["id"])
    (word,) = [w for w in await ac.words() if w["term"] == "Jupyter"]
    assert word["count"] == 2
    assert ac.stats["JUPYTER"].count == 2
    await ac.stop()


async def until(condition, seconds=3.0):
    for _ in range(int(seconds / 0.01)):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met in time")


async def test_accepting_records_the_word_and_counts_letters_saved(config):
    ac = await make(config)
    ac._remember_text("data analysis notebook")
    await spell(ac, "JU")
    word = ac.accept()
    assert (word.gloss, word.kind) == ("JUPYTER", "fingerspell")
    assert not ac.active
    assert ac.metrics()["letters_saved"] == 5  # 7 letters, 2 spelled
    assert ac.metrics()["last_accept"] == {"spelled": 2, "length": 7}
    await until(lambda: len(ac.store.for_term("JUPYTER")) == 4)
    assert ac.store.letters_saved() == (1, 5)
    await ac.stop()


async def test_no_dismisses_then_yes_keeps_the_letters_as_a_new_word(config):
    ac = await make(config)
    await spell(ac, "JUNO")
    assert ac.suggestions == ()  # nothing remembered starts with JUNO
    ac.add("X")
    ac.dismiss()
    assert ac.dismissed
    word = ac.accept()
    assert word.gloss == "JUNOX"
    await until(lambda: ac.store.for_term("JUNOX") != [])
    assert ac.store.for_term("JUNOX")[0].letters_spelled is None  # spelled out, nothing saved
    await ac.stop()


async def test_no_twice_drops_the_letters(config):
    ac = await make(config)
    await spell(ac, "JU")
    ac.dismiss()
    ac.dismiss()
    assert not ac.active
    await ac.stop()


async def test_words_heard_in_captions_are_learned_with_tags(config):
    ac = await make(config, seeded=False)
    ac.bus.publish(Caption("Pranav moved the dashboard to Kubernetes last week.", is_final=True))
    await until(lambda: ac.store.for_term("PRANAV") != [])
    await until(lambda: ac.store.for_term("PRANAV")[0].tags != ())
    (occ,) = ac.store.for_term("PRANAV")
    assert (occ.source, occ.kind) == ("transcript", "name")
    assert "dashboard" in occ.tags  # from the conversation, not the sentence itself
    assert ac.store.for_term("KUBERNETES") != []
    assert ac.store.for_term("DASHBOARD") == []  # ordinary English isn't remembered
    assert (await spell(ac, "PR"))[0] == "Pranav"
    await ac.stop()


async def test_the_same_word_heard_again_soon_is_counted_once(config):
    ac = await make(config, seeded=False)
    for _ in range(3):
        ac.bus.publish(Caption("Ask Pranav.", is_final=True))
    ac.bus.publish(Caption("Pranav", is_final=False))  # partial captions are ignored
    await until(lambda: ac.store.for_term("PRANAV") != [])
    await asyncio.sleep(0.1)
    assert len(ac.store.for_term("PRANAV")) == 1
    await ac.stop()


class FailingTagger:
    async def tag(self, terms, context):
        raise RuntimeError("API down")


async def test_a_tagging_failure_keeps_the_word_untagged(config):
    ac = await make(config, tagger=FailingTagger())
    await spell(ac, "JU")
    ac.accept()
    await until(lambda: len(ac.store.for_term("JUPYTER")) == 4)
    assert ac.store.for_term("JUPYTER")[-1].tags == ()
    await ac.stop()


class KindTagger:
    async def tag(self, terms, context):
        return {t: Tagged("acronym", "API", ("software",)) for t in terms}


async def test_the_tagger_can_fix_kind_and_spelling(config):
    ac = await make(config, tagger=KindTagger(), seeded=False)
    await spell(ac, "API")
    ac.accept()  # nothing remembered: the letters as spelled
    await until(lambda: ac.store.for_term("API") and ac.store.for_term("API")[0].tags)
    assert ac.stats["API"].kind == "acronym"
    assert ac.stats["API"].term == "API"
    await ac.stop()


async def test_nothing_but_the_word_and_tags_is_stored(config):
    ac = await make(config, seeded=False)
    sentence = "Pranav said the secret launch date is March third."
    ac.bus.publish(Caption(sentence, is_final=True))
    await until(lambda: ac.store.for_term("PRANAV") != [])
    await asyncio.sleep(0.05)
    dump = "\n".join(ac.store.db.iterdump())
    assert sentence not in dump and "secret launch date" not in dump
    await ac.stop()


async def test_memory_survives_a_restart(config, vocab_db):
    store = VocabStore(vocab_db)
    store.add([Occurrence("Pranav", "name", "transcript")])
    store.close()
    ac = Autocompleter(Bus(), config, VocabStore(vocab_db), KeywordSearch(config), MockTagger())
    await ac.start()
    assert (await spell(ac, "PR"))[0] == "Pranav"
    await ac.stop()


# ---- through the utterance buffer ----


async def test_letters_then_yes_put_one_word_into_the_utterance(config):
    ac = await make(config)
    buffer = UtteranceBuffer(ac.bus, _translator(config))
    buffer.spelling = ac
    updates = ac.bus.subscribe(AutocompleteUpdate)
    for event in [SignEvent("MEET", 1.0, "isolated"), *map(Letter, "JUP")]:
        await buffer.handle(event)
    if ac._suggesting:
        await ac._suggesting
    await buffer.handle(SignEvent("YES", 1.0, "control"))
    assert [s.gloss for s in buffer.signs] == ["MEET", "JUPYTER"]
    assert buffer.signs[1].kind == "fingerspell"
    updates.close()
    await ac.stop()


async def test_a_sign_after_letters_keeps_them_as_spelled(config):
    ac = await make(config)
    buffer = UtteranceBuffer(ac.bus, _translator(config))
    buffer.spelling = ac
    for event in [*map(Letter, "BOB"), SignEvent("HELP", 1.0, "isolated")]:
        await buffer.handle(event)
    assert [s.gloss for s in buffer.signs] == ["BOB", "HELP"]
    await ac.stop()


def test_closing_the_store_while_a_background_write_runs_is_safe(tmp_path):
    """The engine records a word, then tags it, in worker threads that outlive the task that
    started them, so close() can land mid-write. It must wait, not close under the write."""
    import threading

    store = VocabStore(tmp_path / "vocab.sqlite")
    stop = threading.Event()
    failures: list[BaseException] = []

    def write() -> None:
        try:
            while not stop.is_set():
                occ = Occurrence("Pranav", "name", "fingerspelled")
                store.add([occ])
                store.set_tags(occ.id, ("design", "mockups"), "name")
                store.all()
        except BaseException as exc:  # noqa: BLE001
            failures.append(exc)

    writer = threading.Thread(target=write)
    writer.start()
    time.sleep(0.05)
    store.close()
    stop.set()
    writer.join(5)
    assert not failures, failures

    # After close every call is a no-op, so shutdown never raises or crashes.
    occ = Occurrence("Figma", "term", "fingerspelled")
    store.add([occ])
    store.set_tags(occ.id, ("design",))
    store.delete([occ.id])
    assert store.all() == []
    assert store.for_term("FIGMA") == []
    assert store.get(occ.id) is None
    assert store.delete_term("FIGMA") == []
    assert store.letters_saved() == (0, 0)
    store.close()


def _translator(config):
    from language.mock import MockTranslator

    return MockTranslator(config)
