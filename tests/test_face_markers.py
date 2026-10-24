"""Facial grammar markers: SignEvent.markers, Utterance.gloss tags, and the mock syntax."""

import pytest

from recognition.base import make_sign_event
from recognition.mock import parse_line
from shared.events import SignEvent, Utterance


def sign(gloss, *markers):
    return SignEvent(gloss, 1.0, "isolated", markers=frozenset(markers))


def gloss(*signs):
    return Utterance(signs=signs).gloss


def test_no_markers_by_default():
    assert SignEvent("HELLO", 0.9, "isolated").markers == frozenset()
    assert gloss(sign("HELLO"), sign("fs-SARAH")) == ["HELLO", "fs-SARAH"]


def test_raised_brows_before_the_comment_is_a_topic():
    assert gloss(sign("TITLE", "brows_raised"), sign("RED")) == ["TITLE", "/\\", "RED"]


def test_raised_brows_to_the_end_is_a_yes_no_question():
    signs = [sign(g, "brows_raised") for g in ("YOU", "LIKE", "COFFEE")]
    assert gloss(*signs) == ["YOU", "LIKE", "COFFEE", "[yes/no question]"]


def test_wh_question_negation_and_nod_tags():
    assert gloss(sign("WHERE", "brows_furrowed"), sign("LIVE", "brows_furrowed")) == [
        "WHERE",
        "LIVE",
        "[wh-question]",
    ]
    assert gloss(sign("ME"), sign("LIKE", "head_shake")) == ["ME", "LIKE", "[negation]"]
    assert gloss(sign("YES", "head_nod")) == ["YES", "[affirmation]"]


def test_overlapping_runs_each_get_their_tag():
    signs = [sign("ME", "head_shake"), sign("UNDERSTAND", "head_shake", "brows_furrowed")]
    assert gloss(*signs) == ["ME", "UNDERSTAND", "[wh-question]", "[negation]"]


def test_control_signs_never_carry_markers():
    assert make_sign_event("YES", 1.0, markers=frozenset({"head_nod"})).markers == frozenset()


def test_mock_reads_the_demo_glosses():
    def g(line):
        return Utterance(signs=tuple(e for e in parse_line(line) if e.kind != "control")).gloss

    assert g("food store /\\ ww make") == ["FOOD", "STORE", "/\\", "WW", "MAKE"]
    assert g("tomorrow morning, you-REMIND-me buy milk") == [
        "TOMORROW",
        "MORNING",
        "YOU-REMIND-ME",
        "BUY",
        "MILK",
    ]
    assert g("hello, nice meet-you") == ["HELLO", "NICE", "MEET-YOU"]
    assert g("how you?") == ["HOW", "YOU"]
    assert g("title /\\ red") == ["TITLE", "/\\", "RED"]
    assert g("tomorrow rain [q]") == ["TOMORROW", "RAIN", "[yes/no question]"]
    assert g("tomorrow rain [yes/no question]") == ["TOMORROW", "RAIN", "[yes/no question]"]
    assert g("me like coffee [neg]") == ["ME", "LIKE", "COFFEE", "[negation]"]


def test_mock_marker_covers_back_to_a_comma_or_the_previous_marker():
    events = parse_line("tomorrow, me buy [neg] milk [q]")
    assert [(e.gloss, sorted(e.markers)) for e in events] == [
        ("TOMORROW", []),
        ("ME", ["head_shake"]),
        ("BUY", ["head_shake"]),
        ("MILK", ["brows_raised"]),
    ]


@pytest.mark.parametrize("line", ["[q]", "/\\ hello", "/send [neg]", "hello [huh]"])
def test_mock_rejects_bad_markers(line):
    with pytest.raises(ValueError):
        parse_line(line)
