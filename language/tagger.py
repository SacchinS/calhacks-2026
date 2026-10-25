"""Short topic tags for remembered words, so search can match them to later conversations.

When a word is recorded, the autocompleter asks for 3-5 tags from the last ~30 s of the
conversation (held in memory only) and the word: "Julian" while talking about tennis ->
tennis, doubles partner, weekend. Only the tags are stored; the conversation text is
dropped after the call. Runs in the background: suggestions never wait for it, and a
failure just leaves the word untagged.

`autocomplete.tagger`: claude (Haiku, like the translator), mock (the conversation's own
content words), or auto (claude when `translator: claude`, else mock).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from language.vocab_search import words
from shared.config import Config

log = logging.getLogger(__name__)

SYSTEM = """You label words for a Deaf signer's fingerspelling autocomplete.
For each word, give its kind (name = a person, place or product name; acronym; term =
jargon or anything else), its usual written form (e.g. "API", "Kubernetes", "Priyanka"),
and 3 to 5 short lowercase topic tags (1-3 words each) that describe what the conversation
was about when the word came up, so the word can be suggested in later conversations on the
same topic. Use the conversation only for topics. Never copy sentences into tags, and don't
include other people's names or private details as tags. With no conversation, give tags
for what the word usually relates to."""

SCHEMA = {
    "type": "object",
    "properties": {
        "words": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "kind": {"type": "string", "enum": ["name", "acronym", "term"]},
                    "display": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["word", "kind", "display", "tags"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["words"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Tagged:
    kind: str | None
    display: str | None
    tags: tuple[str, ...]


def clean_tags(tags: list[Any], limit: int = 5) -> tuple[str, ...]:
    out: list[str] = []
    for tag in tags:
        tag = " ".join(str(tag).lower().replace(",", " ").split())[:30]
        if tag and tag not in out:
            out.append(tag)
    return tuple(out[:limit])


class MockTagger:
    """Tags from the conversation's own content words (no API call)."""

    name = "mock"

    async def tag(self, terms: list[str], context: str) -> dict[str, Tagged]:
        content = sorted(words(context) - {t.lower() for t in terms}, key=len, reverse=True)
        tags = clean_tags(content[:4])
        return {t: Tagged(None, None, tags) for t in terms}


class ClaudeTagger:
    name = "claude"

    def __init__(self, config: Config, client: Any = None) -> None:
        self.model = config.get("autocomplete.tagger_model") or config.get(
            "language.claude_model", "claude-haiku-5-5"
        )
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(timeout=10, max_retries=1)
        return self._client

    async def tag(self, terms: list[str], context: str) -> dict[str, Tagged]:
        prompt = json.dumps({"words": terms, "conversation": context or ""})
        message = await self.client.messages.create(
            model=self.model,
            max_tokens=400,
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in message.content if b.type == "text"), "")
        out: dict[str, Tagged] = {}
        by_upper = {t.upper(): t for t in terms}
        for item in json.loads(text).get("words", []):
            term = by_upper.get(str(item.get("word", "")).upper())
            if term is not None:
                display = str(item.get("display") or "").strip() or None
                out[term] = Tagged(item.get("kind"), display, clean_tags(item.get("tags", [])))
        return out


def make_tagger(config: Config) -> MockTagger | ClaudeTagger:
    choice = str(config.get("autocomplete.tagger", "auto"))
    if choice == "auto":
        choice = "claude" if config.translator == "claude" else "mock"
    return ClaudeTagger(config) if choice == "claude" else MockTagger()
