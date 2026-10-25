"""The Claude translator: request shape with a fake client, and real cases with `--live`.

The live cases are the prompt's test set (demo script, glossary, face markers, Siri,
fingerspelling, recognition mistakes). They call the API, so they never run in `make test`.
"""

import re
from types import SimpleNamespace

import pytest

from language.claude import ClaudeTranslator
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


# gloss -> a regex the English must match (case-insensitive)
LIVE_CASES = {
    "FOOD STORE /\\ WW MAKE": r"(build|make|create).*(website|site).*(grocery|food)",
    "TITLE /\\ RED": r"title.*red",
    "TOMORROW MORNING YOU-REMIND-ME BUY MILK": r"^remind me.*(buy|get) milk",
    "TOMORROW RAIN [yes/no question]": r"rain.*tomorrow.*\?$|tomorrow.*rain.*\?$",
    "HELLO NICE MEET-YOU": r"hello.*nice to meet you",
    "HELLO CLEAN MEET-YOU": r"nice to meet you",
    "HOW YOU [wh-question]": r"how are you\?",
    "THANK-YOU": r"^thank you",
    "YOU LIKE COFFEE [yes/no question]": r"^do you like coffee\?",
    "ME LIKE COFFEE [negation]": r"(don't|do not) like coffee",
    "WHERE YOU LIVE [wh-question]": r"where do you live\?",
    "MINEMY NAME fs-SARAH": r"my name is sarah",
    "ME WANT FIX BUG LOGIN PAGE": r"fix.*bug.*login",
    "fs-CSS FILE fs-NAVBAR BLUE": r"(css|navbar).*blue|blue.*(css|navbar)",
    "WHAT TIME NOW [wh-question]": r"what time",
}


@pytest.mark.live
@pytest.mark.parametrize("gloss,pattern", LIVE_CASES.items(), ids=list(LIVE_CASES))
async def test_live_translation(gloss, pattern):
    english = (await ClaudeTranslator(load_config()).translate(gloss.split())).english
    assert re.search(pattern, english, re.I), english
    assert "[" not in english and "/\\" not in english and "fs-" not in english
