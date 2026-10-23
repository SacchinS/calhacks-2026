from recognition.base import Prediction
from recognition.gating import SigningSpace
from recognition.mock import parse_line
from recognition.replay import FixtureLabelClassifier, read_fixture
from recognition.segmenter import Segmenter
from shared.config import ROOT
from shared.events import LandmarkFrame


def run(segmenter, predictions):
    events = [segmenter.push(p) for p in predictions]
    return [e for e in events if e is not None]


def test_emits_once_per_held_sign():
    seg = Segmenter(min_frames=3, confidence_threshold=0.5)
    events = run(seg, [Prediction("HELLO", 0.9)] * 10)
    assert [e.gloss for e in events] == ["HELLO"]
    assert events[0].kind == "isolated"


def test_too_short_or_low_confidence_is_ignored():
    seg = Segmenter(min_frames=3, confidence_threshold=0.5)
    assert run(seg, [Prediction("HELLO", 0.9)] * 2 + [None]) == []
    assert run(seg, [Prediction("HELLO", 0.3)] * 10) == []


def test_same_sign_twice_needs_a_gap():
    seg = Segmenter(min_frames=2, confidence_threshold=0.5)
    sign = Prediction("NO", 0.9)
    events = run(seg, [sign] * 4 + [None] + [sign] * 4)
    assert [(e.gloss, e.kind) for e in events] == [("NO", "control"), ("NO", "control")]


def test_change_of_sign_starts_a_new_one():
    seg = Segmenter(min_frames=2, confidence_threshold=0.5)
    events = run(seg, [Prediction("RED", 0.9)] * 3 + [Prediction("TITLE", 0.8, "fingerspell")] * 3)
    assert [(e.gloss, e.kind) for e in events] == [("RED", "isolated"), ("TITLE", "fingerspell")]


def test_finish_becomes_send_control():
    seg = Segmenter(min_frames=1, confidence_threshold=0.5)
    (event,) = run(seg, [Prediction("FINISH", 0.9)])
    assert (event.gloss, event.kind) == ("SEND", "control")


def test_gating_rejects_resting_hands():
    space = SigningSpace(x_min=0.1, x_max=0.9, y_min=0.05, y_max=0.8)
    up = LandmarkFrame(right_hand=((0.5, 0.4, 0.0),) * 21)
    down = LandmarkFrame(right_hand=((0.5, 0.95, 0.0),) * 21)
    assert space.apply(up).hands_in_signing_space
    assert not space.apply(down).hands_in_signing_space
    assert not space.apply(LandmarkFrame()).hands_in_signing_space


def test_fixture_segments_to_demo_script():
    space = SigningSpace()
    seg = Segmenter(min_frames=5, confidence_threshold=0.6)
    classifier = FixtureLabelClassifier()
    events = []
    for frame in read_fixture(ROOT / "fixtures/landmarks_sample.jsonl"):
        frame = space.apply(frame)
        prediction = classifier.predict(frame) if frame.hands_in_signing_space else None
        if (event := seg.push(prediction)) is not None:
            events.append((event.gloss, event.kind))
    assert events == [
        ("MAKE", "isolated"),
        ("TITLE", "fingerspell"),
        ("RED", "isolated"),
        ("SEND", "control"),
        ("YES", "control"),
    ]


def test_mock_parse_line():
    events = parse_line("me want #title /finish /yes")
    assert [(e.gloss, e.kind) for e in events] == [
        ("ME", "isolated"),
        ("WANT", "isolated"),
        ("TITLE", "fingerspell"),
        ("SEND", "control"),
        ("YES", "control"),
    ]
