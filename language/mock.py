"""Rule-based mock translator for offline demos: joins tokens with light cleanup.

ME WANT FIX BUG LOGIN PAGE -> "I want fix bug login page."
"""

from __future__ import annotations

from language.base import Translator
from shared.events import Translation

# Kaggle vocabulary glosses that are compounds, plus a few pronouns.
WORDS = {
    "ME": "I",
    "I": "I",
    "MINEMY": "my",
    "WEUS": "we",
    "HESHEIT": "it",
    "YOURSELF": "yourself",
    "THANKYOU": "thank you",
    "HAVETO": "have to",
    "CALLONPHONE": "call",
    "FRENCHFRIES": "french fries",
    "GLASSWINDOW": "window",
    "ICECREAM": "ice cream",
}
QUESTION_WORDS = {"WHERE", "WHO", "WHY", "WHAT", "HOW", "WHEN"}
# Face-marker tags (see shared/events.py MARKER_TAGS): questions end in "?", a head shake
# reads as "not", topic brows and nods add no words.
QUESTION_TAGS = {"[yes/no question]", "[wh-question]"}
TAG_WORDS = {"/\\": None, "[affirmation]": None, "[negation]": "not"}
TAG_WORDS |= dict.fromkeys(QUESTION_TAGS)


class MockTranslator(Translator):
    provider = "mock"

    async def translate(self, gloss: list[str]) -> Translation:
        words = []
        for token in gloss:
            if token in TAG_WORDS:
                if TAG_WORDS[token]:
                    words.append(TAG_WORDS[token])
                continue
            token = token.removeprefix("fs-")
            words.append(WORDS.get(token.upper(), token.lower()))
        if not words:
            return Translation(gloss=list(gloss), english="", provider=self.provider)
        text = " ".join(words)
        text = text[0].upper() + text[1:]
        is_question = any(
            t in QUESTION_TAGS or t.removeprefix("fs-").upper() in QUESTION_WORDS for t in gloss
        )
        return Translation(
            gloss=list(gloss),
            english=text + ("?" if is_question else "."),
            provider=self.provider,
        )
