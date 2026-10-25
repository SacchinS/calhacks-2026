"""The Claude translator: request shape with a fake client, and real cases with `--live`.

The live cases are the prompt's test set: the Meet demo's greeting, fingerspelled names and
terms the autocomplete inserts, face markers, and recognition mistakes. They call the API, so
they never run in `make test`.
"""

import asyncio
import re
import time
from types import SimpleNamespace

import pytest

from language.claude import ClaudeTranslator
from language.mock import MockTranslator
from language.utterance import UtteranceBuffer
from shared.config import load_config


class FakeMessages:
    def __init__(self, reply, stop_reason="end_turn"):
        self.reply = reply
        self.stop_reason = stop_reason
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        blocks = [SimpleNamespace(type="text", text=self.reply)] if self.reply else []
        return SimpleNamespace(content=blocks, stop_reason=self.stop_reason)


def translator(reply="Make the title red.", stop_reason="end_turn"):
    messages = FakeMessages(reply, stop_reason)
    client = SimpleNamespace(messages=messages)
    return ClaudeTranslator(load_config(), client=client), messages


async def test_sends_only_the_gloss_as_text_with_the_prompt():
    t, messages = translator()
    result = await t.translate(["TITLE", "/\\", "RED"])
    assert (result.english, result.provider, result.gloss) == (
        "Make the title red.",
        "claude",
        ["TITLE", "/\\", "RED"],
    )
    (call,) = messages.calls
    assert call["messages"] == [{"role": "user", "content": "TITLE /\\ RED"}]
    assert call["model"] == "claude-haiku-5-5"
    assert "ASL gloss" in call["system"][0]["text"]


@pytest.mark.parametrize("reply,stop", [("", "end_turn"), ("x", "refusal")])
async def test_empty_or_refused_replies_raise_so_the_buffer_falls_back(reply, stop):
    t, _ = translator(reply, stop)
    with pytest.raises((ValueError, RuntimeError)):
        await t.translate(["HELLO"])


async def test_warm_up_writes_the_prompt_cache_and_asks_for_no_output():
    t, messages = translator()
    await t.warm()
    (call,) = messages.calls
    assert call["max_tokens"] == 0  # prefill only: the cache write, no output tokens
    assert "stream" not in call and "format" not in call.get("output_config", {})
    assert call["system"] == [
        {
            "type": "text",
            "text": t.system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert call["messages"] == [{"role": "user", "content": "warmup"}]


async def test_the_warmed_prompt_is_the_one_translation_sends():
    """The cache is a prefix match, so a warm-up with a different system block would write
    an entry no translation ever reads."""
    t, messages = translator()
    await t.warm()
    await t.translate(["HELLO"])
    warm, real = messages.calls
    assert warm["system"] == real["system"]
    assert (warm["model"], warm["thinking"]) == (real["model"], real["thinking"])
    assert warm["output_config"] == real["output_config"]


async def test_the_buffer_warms_the_translator_without_waiting_or_raising():
    from shared.bus import Bus

    class SlowFailingTranslator(MockTranslator):
        def __init__(self, config):
            super().__init__(config)
            self.warmed = asyncio.Event()

        async def warm(self):
            self.warmed.set()
            raise RuntimeError("no network at startup")

    translator_ = SlowFailingTranslator(load_config())
    buffer = UtteranceBuffer(Bus(), translator_)
    await buffer.start()  # must not raise, and must not wait for the warm-up
    await asyncio.wait_for(translator_.warmed.wait(), 2)
    await buffer.stop()


async def test_a_translator_with_nothing_to_warm_does_nothing():
    await MockTranslator(load_config()).warm()


# gloss -> a regex the English must match (case-insensitive). The glosses are the demo's
# (docs/asl-demo-script-research.md, Moment 3); fingerspelled words arrive as `fs-WORD`,
# uppercase, which is what Utterance.gloss builds when the autocomplete accepts a word.
LIVE_CASES = {
    # The demo call: the greeting, then the words the autocomplete filled in.
    "HELLO fs-PRIYANKA NICE MEET-YOU": r"hello,? priyanka.*nice to meet you",
    "HELLO NICE MEET-YOU": r"hello.*nice to meet you",
    "fs-FIGMA": r"^figma\b",
    "HOW YOU [wh-question]": r"how are you\?",
    "FINE": r"\bfine\b",
    "THANK-YOU": r"^thank you",
    # A fingerspelled term mid-sentence, the way the autocomplete inserts it.
    "FEEDBACK GO fs-FIGMA": r"feedback.*figma|figma.*feedback",
    "MINEMY NAME fs-SARAH": r"my name is sarah",
    # Recognition mistakes. CLEAN and NICE are one sign; MEET can come back without the
    # trained MEET-YOU. Both must still read as the greeting, not a new sentence.
    "HELLO CLEAN MEET-YOU": r"nice to meet you",
    "NICE MEET fs-PRIYANKA": r"(nice to )?meet you,? priyanka|nice to meet you",
    # Face markers.
    "SETTINGS PAGE /\\ NEXT": r"settings page.*next|next.*settings page",
    "TOMORROW RAIN [yes/no question]": r"rain.*tomorrow.*\?$|tomorrow.*rain.*\?$",
    "YOU LIKE COFFEE [yes/no question]": r"^do you like coffee\?",
    "ME LIKE COFFEE [negation]": r"(don't|do not) like coffee",
    "WHERE YOU LIVE [wh-question]": r"where do you live\?",
    "WHAT TIME NOW [wh-question]": r"what time",
}

# It's spoken in a call, so a slow sentence is a long silence for everyone else.
MAX_SECONDS = 2.0


@pytest.mark.live
async def test_live_warm_up_means_the_first_sentence_reads_the_cache():
    """Without this the signer's first sentence of a call pays for the connection and the
    cache write; warm-up moves both to startup."""
    t = ClaudeTranslator(load_config())
    usage = []
    create = t.client.messages.create

    async def spy(**kwargs):
        message = await create(**kwargs)
        usage.append(message.usage)
        return message

    t.client.messages.create = spy
    await t.warm()
    started = time.perf_counter()
    await t.translate(["HELLO", "fs-PRIYANKA", "NICE", "MEET-YOU"])
    seconds = time.perf_counter() - started
    _, after = usage
    print(
        f"\nfirst sentence after warm-up: {seconds * 1000:.0f} ms, "
        f"{after.cache_read_input_tokens} prompt tokens from cache"
    )
    assert after.cache_read_input_tokens > 0
    assert seconds < MAX_SECONDS


@pytest.mark.live
@pytest.mark.parametrize("gloss,pattern", LIVE_CASES.items(), ids=list(LIVE_CASES))
async def test_live_translation(gloss, pattern):
    started = time.perf_counter()
    english = (await ClaudeTranslator(load_config()).translate(gloss.split())).english
    seconds = time.perf_counter() - started
    print(f"\n{seconds * 1000:7.0f} ms  {gloss}  ->  {english}")
    assert re.search(pattern, english, re.I), english
    assert "[" not in english and "/\\" not in english and "fs-" not in english
    assert seconds < MAX_SECONDS, f"{seconds:.2f} s is too slow to speak in a call"
