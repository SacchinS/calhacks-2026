"""Words worth remembering from the other side's captions: names, acronyms and jargon.

Heuristics only: an all-caps token (API, PR), a capitalized word that isn't ordinary English
(Priyanka, Kubernetes), or a long lowercase word that isn't either (kubectl). "Ordinary
English" is the lowercase entries of macOS's word list (/usr/share/dict/words), plus a few
spoken words it lacks. The tagger (language/tagger.py) can correct the kind later.

`keyterms` goes the other way: the words we already remember are given to Cartesia Ink when
captions start, so it spells them the way the signer does.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable
from pathlib import Path

from language.vocab import Occurrence, build_stats

DICTIONARY = Path("/usr/share/dict/words")
EXTRA_COMMON = frozenset(
    """okay ok yeah yep nope gonna wanna gotta hey hi hello thanks let's let i'm i'll i've
    you're we're they're that's it's there's what's don't can't won't didn't doesn't isn't
    aren't wasn't couldn't shouldn't wouldn't email online offline website app apps
    monday tuesday wednesday thursday friday saturday sunday january february march april
    may june july august september october november december""".split()
)
NOT_ACRONYMS = frozenset({"I", "OK", "A", "TV", "AM", "PM"})
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9'’-]*[A-Za-z0-9]|[A-Za-z]")


@functools.cache
def common_words() -> frozenset[str]:
    try:
        lines = DICTIONARY.read_text(errors="ignore").split()
    except OSError:
        lines = []
    return frozenset(w for w in lines if w.islower()) | EXTRA_COMMON


def is_common(word: str) -> bool:
    """Ordinary English, allowing plurals and simple endings ("filters", "charted")."""
    w = word.lower().replace("’", "'").removesuffix("'s")
    common = common_words()
    forms = {w}
    for suffix, back in (
        ("ies", "y"),
        ("es", ""),
        ("s", ""),
        ("ed", ""),
        ("ed", "e"),
        ("ing", ""),
        ("ing", "e"),
        ("ly", ""),
        ("er", ""),
        ("ers", ""),
    ):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            forms.add(w[: -len(suffix)] + back)
    return any(f in common for f in forms)


def keyterms(
    occurrences: Iterable[Occurrence],
    names: Iterable[str] = (),
    limit: int = 100,
    max_chars: int = 1200,
) -> list[str]:
    """The words to give Cartesia Ink as keyterms, so captions spell them the way we do.

    The signer's own name first (a caption that misspells it misses a mention alert), then
    the remembered words, most-used first and most-recent to break ties. Ordinary English is
    left out: Ink reads it correctly already, and the limits (100 terms, 1200 characters)
    are better spent on names and jargon.
    """
    out: list[str] = []
    seen: set[str] = set()
    chars = 0

    def add(word: str) -> bool:
        nonlocal chars
        word = word.strip()
        key = word.casefold()
        if not word or key in seen:
            return True
        if len(out) >= limit or chars + len(word) > max_chars:
            return False
        out.append(word)
        seen.add(key)
        chars += len(word)
        return True

    for name in names:
        if not add(name):
            return out
    ranked = sorted(
        build_stats(occurrences).values(), key=lambda s: (-s.count, -s.last_used, s.term)
    )
    for stats in ranked:
        if is_common(stats.term):
            continue
        if not add(stats.term):
            break
    return out


def extract_terms(text: str) -> list[tuple[str, str]]:
    """[(display form, kind)] for the likely names, acronyms and jargon in one caption."""
    found: dict[str, tuple[str, str]] = {}
    for token in TOKEN.findall(text):
        token = token.replace("’", "'").removesuffix("'s")
        key = token.upper()
        if key in found:
            continue
        letters = re.sub(r"[^A-Za-z]", "", token)
        if 2 <= len(letters) <= 6 and token.isupper() and token not in NOT_ACRONYMS:
            found[key] = (token, "acronym")
        elif token[0].isupper() and len(letters) >= 3 and not is_common(token):
            found[key] = (token, "name")
        elif token.islower() and len(letters) >= 6 and not is_common(token):
            found[key] = (token, "term")
    return list(found.values())
