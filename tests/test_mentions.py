"""Mention alerts: the signer's name in the captions, once per turn, then the full question."""

import pytest

from captions.mentions import MentionDetector, is_question
from shared.bus import Bus
from shared.config import Config
from shared.events import Caption, Mention


def detector(name="Sam Lee", **meet):
    bus = Bus()
    d = MentionDetector(bus, Config(sections={"meet": {"signer_name": name, **meet}}))
    return d, bus.subscribe(Mention)


def drain(sub):
    out = []
    while not sub.queue.empty():
        out.append(sub.get_nowait())
    return out


def test_alerts_once_on_the_partial_then_again_with_the_question():
    d, sub = detector()
    for text in ["Sam", "Sam, can you", "Sam, can you take the dashboard"]:
        d.on_caption(Caption(text, is_final=False))
    d.on_caption(Caption("Sam, can you take the dashboard ticket by Friday?", is_final=True))
    first, last = drain(sub)
    assert (first.text, first.final) == ("Sam", False)
    assert last.final and last.question and last.turn == first.turn
    assert "dashboard ticket" in last.text


def test_each_turn_alerts_separately_and_other_names_dont():
    d, sub = detector()
    d.on_caption(Caption("Alex, can you review it?"))
    d.on_caption(Caption("Thanks, Sam's part looks good."))
    d.on_caption(Caption("sam lee, are you there?"))
    mentions = drain(sub)
    assert [(m.turn, m.question) for m in mentions] == [(1, False), (2, True)]


def test_nicknames_and_no_name():
    d, sub = detector(name="Samantha", mention_names=["Sammy"])
    d.on_caption(Caption("Sammy, quick question?"))
    assert len(drain(sub)) == 1
    d, sub = detector(name="")
    d.on_caption(Caption("Hey, can you hear me?"))
    assert drain(sub) == []


def test_questions_alert_in_one_to_one_mode():
    d, sub = detector(name="", alert_on_questions=True)
    d.on_caption(Caption("Can you take the dashboard ticket?"))
    d.on_caption(Caption("Great, thanks."))
    assert [m.question for m in drain(sub)] == [True]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Can you do it", True),
        ("What do you think", True),
        ("Is it Friday?", True),
        ("Okay.", False),
    ],
)
def test_is_question(text, expected):
    assert is_question(text) is expected


def test_the_name_isnt_matched_inside_other_words():
    d, sub = detector(name="Al")
    d.on_caption(Caption("Also, the alert is fine."))
    assert drain(sub) == []
