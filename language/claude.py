"""Claude translator (Anthropic API): ASL gloss -> natural English.

The system prompt is `language/prompts/gloss_to_english.md`. Only the recognized sign words
are sent, as text; never video. A failure raises, and the utterance buffer shows a warning
and falls back to the mock translator, so `translator: claude` never crashes the app.
"""

from __future__ import annotations

import logging

import anthropic

from language.base import Translator
from shared.config import Config
from shared.events import Translation

log = logging.getLogger(__name__)


class ClaudeTranslator(Translator):
    provider = "claude"

    def __init__(self, config: Config, client: anthropic.AsyncAnthropic | None = None) -> None:
        super().__init__(config)
        self.model = config.get("language.claude_model", "claude-haiku-5-5")
        self.max_tokens = int(config.get("language.max_tokens", 200))
        self.timeout = float(config.get("language.timeout_seconds", 10))
        self.system_prompt = config.path("language.prompt_file").read_text()
        # Reads ANTHROPIC_API_KEY (loaded from .env by shared.config).
        self.client = client or anthropic.AsyncAnthropic(timeout=self.timeout, max_retries=1)

    def _system(self) -> list[dict]:
        """The prompt, cached: it's the same ~1,300 tokens on every sentence of the call."""
        return [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    async def warm(self) -> None:
        """Write the prompt into the cache before the signer's first sentence.

        `max_tokens=0` runs prefill and returns no content, so it costs the cache write and
        no output. It also opens the TLS connection, which the first call would otherwise
        pay for. No streaming and no structured output: both are rejected with max_tokens 0.
        """
        await self.client.messages.create(
            model=self.model,
            max_tokens=0,
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            system=self._system(),
            messages=[{"role": "user", "content": "warmup"}],
        )
        log.debug("claude: prompt cache warmed")

    async def translate(self, gloss: list[str]) -> Translation:
        message = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            # A short, latency-sensitive rewrite: no thinking, low effort.
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            system=self._system(),
            messages=[{"role": "user", "content": " ".join(gloss)}],
        )
        if message.stop_reason == "refusal":
            raise RuntimeError("Claude declined to translate this")
        english = "".join(b.text for b in message.content if b.type == "text").strip()
        if not english:
            raise ValueError("Claude returned no text")
        log.debug("claude: %s -> %s", gloss, english)
        return Translation(gloss=list(gloss), english=english, provider=self.provider)
