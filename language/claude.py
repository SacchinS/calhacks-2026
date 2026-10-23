"""Claude translator (Anthropic API). STUB: raises NotImplementedError.

The utterance buffer catches the error, shows a warning in the UI, and falls back to the
mock translator, so selecting `translator: claude` never crashes the app.
"""

from __future__ import annotations

import logging

from language.base import Translator
from shared.config import Config
from shared.events import Translation

log = logging.getLogger(__name__)


class ClaudeTranslator(Translator):
    provider = "claude"

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.model = config.get("language.claude_model", "claude-haiku-5-5")
        self.max_tokens = int(config.get("language.max_tokens", 200))
        self.system_prompt = config.path("language.prompt_file").read_text()
        log.warning("ClaudeTranslator is a stub (model %s)", self.model)

    async def translate(self, gloss: list[str]) -> Translation:
        # TODO(Person B): call Claude with the official `anthropic` SDK:
        #   client = anthropic.AsyncAnthropic()   # reads ANTHROPIC_API_KEY from .env (once)
        #   message = await client.messages.create(
        #       model=self.model, max_tokens=self.max_tokens, system=self.system_prompt,
        #       messages=[{"role": "user", "content": " ".join(gloss)}])
        #   english = the text block(s) of `message`, stripped.
        # Return Translation(gloss=gloss, english=english, provider="claude").
        # Aim for < ~2 s; raise on API errors (the buffer falls back to the mock).
        raise NotImplementedError("ClaudeTranslator is a stub")
