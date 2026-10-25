"""The real tagger (Claude Haiku) on the demo's words: the kind, the written form, and 3 to 5
short topic tags. Only the tags are stored, so they have to describe the topic without copying
the conversation or naming anyone else. Run with `uv run pytest --live`."""

import re

import pytest

from language.tagger import ClaudeTagger
from shared.config import Config, load_config

DEMO_CAPTION = "Hi, I'm Priyanka, I'm designing the new app. The mockups are all in Figma."
TENNIS = "Julian and I played doubles again on Saturday; we need a fourth next weekend."
BACKEND = "The API is returning a 500 on the signup endpoint since yesterday's deploy."


def _anthropic_key() -> bool:
    load_config()  # reads .env into the environment, which Config.secret looks at
    return bool(Config.secret("ANTHROPIC_API_KEY"))


needs_claude = pytest.mark.skipif(not _anthropic_key(), reason="ANTHROPIC_API_KEY isn't set")

# Words that must never appear in a tag: other people in the conversation, and the word the
# tags belong to (a tag repeating the word tells search nothing).
OTHER_NAMES = {"priyanka", "julian", "sam", "marisol"}


def check(tagged, word: str, context: str, kind: str | None = None) -> None:
    """The word is already written the way it should be, so `display` must come back as it is.
    `kind` is only checked where it's unambiguous: Figma is both a product name and jargon, and
    the prompt counts a product name as `name`, so Claude says either. Nothing depends on it
    either way, since ranking never reads the kind."""
    assert tagged is not None, f"no tags came back for {word}"
    assert tagged.kind in ("name", "acronym", "term"), f"{word}: kind {tagged.kind!r}"
    if kind is not None:
        assert tagged.kind == kind, f"{word}: kind {tagged.kind!r}, expected {kind!r}"
    assert tagged.display == word, f"{word}: display {tagged.display!r}"
    assert 3 <= len(tagged.tags) <= 5, f"{word}: {len(tagged.tags)} tags: {tagged.tags}"
    sentences = {s.strip().lower() for s in re.split(r"[.;?]", context) if s.strip()}
    for tag in tagged.tags:
        assert tag == tag.lower(), f"{word}: tag {tag!r} isn't lowercase"
        assert 1 <= len(tag.split()) <= 3, f"{word}: tag {tag!r} isn't 1 to 3 words"
        assert tag not in sentences, f"{word}: tag {tag!r} copies a sentence"
        assert len(tag) < 30, f"{word}: tag {tag!r} is too long to be a topic"
        for name in OTHER_NAMES - {word.lower()}:
            assert name not in tag, f"{word}: tag {tag!r} names {name}"


@pytest.mark.live
@needs_claude
async def test_live_tagger_on_the_demo_words():
    tagger = ClaudeTagger(load_config())
    tagged = await tagger.tag(["Priyanka", "Figma"], DEMO_CAPTION)
    check(tagged.get("Priyanka"), "Priyanka", DEMO_CAPTION, kind="name")
    check(tagged.get("Figma"), "Figma", DEMO_CAPTION)
    print(f"\nPriyanka: {tagged['Priyanka'].tags}")
    print(f"Figma: {tagged['Figma'].tags}")


@pytest.mark.live
@needs_claude
async def test_live_tagger_separates_a_name_from_an_acronym():
    tagger = ClaudeTagger(load_config())
    julian = await tagger.tag(["Julian"], TENNIS)
    check(julian.get("Julian"), "Julian", TENNIS, kind="name")
    api = await tagger.tag(["API"], BACKEND)
    check(api.get("API"), "API", BACKEND, kind="acronym")
    print(f"\nJulian: {julian['Julian'].tags}")
    print(f"API: {api['API'].tags}")


@pytest.mark.live
@needs_claude
async def test_live_tagger_tags_the_topic_not_the_sentence():
    """The tags are what search matches a later conversation against, so they have to be
    about the topic: a tennis conversation should give tennis words."""
    tagger = ClaudeTagger(load_config())
    tagged = await tagger.tag(["Julian"], TENNIS)
    tags = " ".join(tagged["Julian"].tags)
    assert any(w in tags for w in ("tennis", "doubles", "weekend", "sport")), tags
