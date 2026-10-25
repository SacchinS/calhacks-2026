"""Fingerspelled letters (recognition/fingerspelling.py): the model's input and letter
choice, the reader's hold / repeat / start / end rules, and spelling inside the frame
pipeline. A scripted stand-in model reads the letter off the hand, so no ONNX is needed."""

import asyncio

import numpy as np
import pytest

from recognition.base import FrameClassifier, FrameRecognizer, Prediction
from recognition.fingerspelling import LetterModel, LetterReader, normalize
from recognition.gating import SigningSpace
from shared.bus import Bus
from shared.config import Config
from shared.events import LandmarkFrame, Letter, SignEvent

SPACE = SigningSpace()
FPS = 30


def hand(letter: str | None, x: float = 0.5, y: float = 0.5) -> tuple:
    """A 21-point hand, wrist at (x, y), palm 0.1 long; the letter rides on the last z."""
    points = [(x + 0.01 * i, y - 0.005 * i, 0.0) for i in range(21)]
    points[9] = (x, y - 0.1, 0.0)
    points[20] = (points[20][0], points[20][1], float(ord(letter)) if letter else 0.0)
    return tuple(points)


class ScriptedModel:
    """Says the letter written on the hand, at `confidence`."""

    def __init__(self, confidence=0.9):
        self.confidence = confidence

    def predict(self, points):
        code = points[20][2]
        return (chr(int(code)), self.confidence) if code else None


def frames(script, start=0.0):
    """[(letter or None, seconds, wrist x)] -> right-hand frames at 30 fps."""
    t, out = start, []
    for letter, seconds, x in script:
        for _ in range(int(seconds * FPS)):
            out.append(LandmarkFrame(right_hand=hand(letter, x), ts=t))
            t += 1 / FPS
    return out


def read(reader, script):
    """Push the script's frames (time carries on from the last read) -> the letters out."""
    letters, played = [], frames(script, start=getattr(reader, "clock", 0.0))
    for frame in played:
        letters += reader.push(frame, SPACE)
    if played:
        reader.clock = played[-1].ts + 1 / FPS
    return "".join(letter.letter for letter in letters)


def reader(**settings):
    return LetterReader(Config(sections={"recognition": settings}), ScriptedModel())


def test_input_is_wrist_centered_scaled_and_mirrorable():
    x = normalize(hand("A", 0.3, 0.6)).reshape(21, 3)
    assert np.allclose(x[0], 0) and np.isclose(np.linalg.norm(x[9]), 1.0)
    mirrored = normalize(hand("A", 0.3, 0.6), mirrored=True).reshape(21, 3)
    assert np.allclose(mirrored[:, 0], -x[:, 0]) and np.allclose(mirrored[:, 1], x[:, 1])


def test_digits_are_ignored_and_auto_keeps_the_surer_orientation():
    classes = [*"0123456789", *"ABCDEFGHIJKLMNOPQRSTUVWXYZ"]

    def run(x):  # as seen: "2" then V; mirrored: a clear W
        logits = np.zeros(36, dtype=np.float32)
        if x[0, 3] >= 0:
            logits[2], logits[10 + ord("V") - 65] = 9, 5
        else:
            logits[10 + ord("W") - 65] = 9
        return logits[None]

    shape = hand("A")
    as_is = LetterModel(
        Config(sections={"recognition": {"letter_orientation": "as_is"}}), run, classes
    )
    assert as_is.predict(shape)[0] == "V"  # the digit 2 is dropped
    auto = LetterModel(Config(), run, classes)
    letter, confidence = auto.predict(shape)
    assert letter == "W" and auto.last_orientation == "mirrored" and confidence > 0.9


def test_a_letter_counts_once_held_and_spelling_starts_at_the_second():
    r = reader()
    assert read(r, [("P", 0.5, 0.5)]) == ""  # one letter could be a sign's handshape
    assert not r.spelling
    assert read(r, [("R", 0.5, 0.5)]) == "PR"  # the second within the gap: both come out
    assert r.spelling
    assert read(r, [("I", 0.5, 0.5)]) == "I"


def test_holding_longer_or_flickering_does_not_repeat():
    r = reader()
    assert read(r, [("P", 0.4, 0.5), ("R", 2 / FPS, 0.5), ("P", 0.4, 0.5), ("R", 0.5, 0.5)]) == "PR"
    assert read(r, [("R", 1.0, 0.5)]) == ""  # still R: once is enough


def test_a_double_letter_needs_a_small_slide():
    r = reader()
    assert read(r, [("B", 0.4, 0.5), ("A", 0.4, 0.5), ("L", 0.4, 0.5), ("L", 0.4, 0.55)]) == "BALL"


def test_too_short_low_confidence_or_two_hands_count_for_nothing():
    r = reader()
    assert read(r, [("P", 0.1, 0.5), ("R", 0.1, 0.5)]) == ""  # shorter than the hold
    quiet = LetterReader(Config(), ScriptedModel(confidence=0.3))
    assert read(quiet, [("P", 0.5, 0.5), ("R", 0.5, 0.5)]) == ""
    both = LetterReader(Config(), ScriptedModel())
    two = [
        LandmarkFrame(right_hand=hand("P"), left_hand=hand("P", 0.4), ts=i / FPS) for i in range(30)
    ]
    assert all(both.push(f, SPACE) == [] for f in two)


def test_spelling_ends_after_a_pause_and_the_next_word_starts_over():
    r = reader(letter_end_seconds=1.0)
    assert read(r, [("P", 0.4, 0.5), ("R", 0.4, 0.5)]) == "PR"
    assert read(r, [(None, 1.5, 0.5)]) == "" and not r.spelling
    assert read(r, [("K", 0.4, 0.5)]) == ""  # a new word's first letter waits again


class LabelSigns(FrameClassifier):
    """The frame's label as an isolated sign (YES as a control sign)."""

    def predict(self, frame):
        return Prediction(frame.label, 0.9) if frame.label else None


class Scripted(FrameRecognizer):
    name = "scripted"

    def __init__(self, bus, config, script):
        super().__init__(bus, config)
        self.script = script

    async def frames(self):
        for frame in self.script:
            yield frame
        await asyncio.sleep(0)

    def classifiers(self):
        return [LabelSigns()]

    def letter_reader(self):
        return LetterReader(self.config, ScriptedModel())


@pytest.mark.asyncio
async def test_while_spelling_only_control_signs_get_through():
    def signed(letter, seconds, label=None, start=0.0):
        n = int(seconds * FPS)
        return [
            LandmarkFrame(right_hand=hand(letter), label=label, ts=start + i / FPS)
            for i in range(n)
        ]

    script = signed("P", 0.4) + signed("R", 0.4, start=0.4)  # spelling P, R
    script += signed("I", 0.5, label="HELLO", start=0.8)  # the sign model misreads the hold
    script += signed(None, 0.6, label="YES", start=1.3)  # YES takes the suggestion
    script += signed(None, 0.5, label="HELLO", start=1.9)  # a real sign afterwards
    bus = Bus()
    events = bus.subscribe(Letter, SignEvent)
    recognizer = Scripted(bus, Config(), script)
    await recognizer.start()
    await asyncio.wait_for(recognizer._task, 5)
    out = []
    while not events.queue.empty():
        e = events.get_nowait()
        out.append(e.letter if isinstance(e, Letter) else e.gloss)
    assert out == ["P", "R", "I", "YES", "HELLO"]


def test_auto_orientation_sticks_with_the_surer_one():
    classes = [*"0123456789", *"ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    flips = iter(range(1, 1000))

    def run(x):  # as seen: always a sure R; mirrored: U, now and then a little surer
        logits = np.zeros(36, dtype=np.float32)
        if x[0, 3] >= 0:
            logits[10 + ord("R") - 65] = 6
        else:
            logits[10 + ord("U") - 65] = 7 if next(flips) % 5 == 0 else 2
        return logits[None]

    model = LetterModel(Config(), run, classes)
    letters = {model.predict(hand("A"))[0] for _ in range(30)}
    assert letters == {"R"} and model.last_orientation == "as_is"


def test_one_unsure_frame_does_not_break_a_hold():
    class Dipping(ScriptedModel):
        def __init__(self):
            super().__init__()
            self.n = 0

        def predict(self, points):
            self.n += 1
            letter, _ = super().predict(points)
            return (letter, 0.3 if self.n % 4 == 0 else 0.9)  # every 4th frame is unsure

    r = LetterReader(Config(), Dipping())
    assert read(r, [("P", 0.4, 0.5), ("R", 0.4, 0.5)]) == "PR"
