"""`keyterms`: which remembered words go to Cartesia Ink when captions start, in what order.

Ink takes at most 100 terms totalling 1200 characters, so the order decides what gets in: the
signer's own name first, because a caption that misspells it misses a mention alert.
"""

import time

from language.vocab import Occurrence
from language.vocab_terms import keyterms

DAY = 86400


def used(term: str, times: int = 1, days_ago: float = 0, kind: str = "name") -> list[Occurrence]:
    now = time.time()
    return [
        Occurrence(term, kind, "fingerspelled", used_at=now - days_ago * DAY) for _ in range(times)
    ]


def test_the_signers_name_and_nicknames_come_first():
    occurrences = used("Pranav", times=5) + used("Figma", times=9, kind="term")
    assert keyterms(occurrences, ["Sam", "Sammy"]) == ["Sam", "Sammy", "Figma", "Pranav"]


def test_remembered_words_are_ranked_by_uses_then_by_last_use():
    """Names that aren't English words: keyterms skips common words, and macOS's word list
    has "once", "twice" and "thrice"."""
    occurrences = (
        used("Onyeka", times=1)
        + used("Thandiwe", times=3)
        + used("Tobiah", times=2, days_ago=30)
        + used("Tobiko", times=2, days_ago=1)
    )
    assert keyterms(occurrences) == ["Thandiwe", "Tobiko", "Tobiah", "Onyeka"]


def test_a_name_already_remembered_is_not_repeated():
    """Case-insensitively: the signer's name is whatever they typed in Settings."""
    assert keyterms(used("pranav", times=3), ["PRANAV"]) == ["PRANAV"]


def test_the_display_form_is_sent():
    """What the signer spells wins, so Ink is told the spelling the app will show."""
    assert keyterms(used("Kubernetes"), []) == ["Kubernetes"]


def test_ordinary_english_is_left_out():
    """Ink gets these right already, and the limits are better spent on names and jargon."""
    occurrences = used("Monday", times=9, kind="term") + used("Pranav")
    assert keyterms(occurrences) == ["Pranav"]


def test_it_stops_at_the_term_limit():
    names = ["Ada", "Bao", "Chidi", "Dana", "Esme"]
    occurrences = [o for i, name in enumerate(names) for o in used(name, times=len(names) - i)]
    assert keyterms(occurrences, limit=3) == ["Ada", "Bao", "Chidi"]


def test_it_stops_at_the_character_limit():
    occurrences = used("Pranav", times=3) + used("Bartholomew", times=2) + used("Jo")
    # "Pranav" (6) + "Bartholomew" (11) is 17; 18 leaves no room for "Jo".
    assert keyterms(occurrences, max_chars=18) == ["Pranav", "Bartholomew"]
    assert keyterms(occurrences, max_chars=6) == ["Pranav"]


def test_a_name_too_long_for_the_budget_doesnt_block_the_rest():
    """The signer's name is added first, so if it doesn't fit nothing else should sneak in."""
    assert keyterms(used("Pranav"), ["Bartholomew"], max_chars=5) == []


def test_no_words_and_no_names_is_empty():
    assert keyterms([], []) == []
