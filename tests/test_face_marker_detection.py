"""Facial grammar detection from face landmarks, on a synthetic face."""

from recognition.face_markers import (
    LEFT_BROW,
    RIGHT_BROW,
    FaceMarkerDetector,
    MarkerTally,
    face_measures,
    swings,
)
from shared.config import Config
from shared.events import LandmarkFrame


def face(brow_lift=0.0, inner_gap=0.04, nose_dx=0.0, nose_dy=0.0):
    pts = [(0.5, 0.4, 0.0)] * 468
    pts = list(pts)
    set_ = {
        33: (0.45, 0.4),
        263: (0.55, 0.4),
        159: (0.46, 0.39),
        386: (0.54, 0.39),
        234: (0.40, 0.42),
        454: (0.60, 0.42),
        10: (0.5, 0.33),
        152: (0.5, 0.5),
        1: (0.5 + nose_dx, 0.42 + nose_dy),
    }
    for i in LEFT_BROW + RIGHT_BROW:
        set_[i] = (0.5, 0.37 - brow_lift)
    set_[107] = (0.5 - inner_gap / 2, 0.37 - brow_lift)
    set_[336] = (0.5 + inner_gap / 2, 0.37 - brow_lift)
    for i, (x, y) in set_.items():
        pts[i] = (x, y, 0.0)
    return tuple(pts)


def frame(signing=True, **face_args):
    return LandmarkFrame(face=face(**face_args), hands_in_signing_space=signing)


def detector():
    d = FaceMarkerDetector(Config(sections={"recognition": {"face_markers": True}}))
    for _ in range(20):
        d.update(frame(signing=False))  # resting: the neutral face
    return d


def test_measures_are_scale_free():
    m = face_measures(face())
    assert round(m["height"], 3) == 0.2 and abs(m["yaw"]) < 1e-6


def test_off_by_default():
    d = FaceMarkerDetector(Config())
    assert d.update(frame(brow_lift=0.02)) == frozenset()


def test_neutral_face_has_no_markers():
    d = detector()
    assert d.update(frame()) == frozenset()


def test_raised_and_furrowed_brows():
    assert detector().update(frame(brow_lift=0.01)) == {"brows_raised"}
    assert detector().update(frame(brow_lift=-0.005, inner_gap=0.03)) == {"brows_furrowed"}


def test_head_shake_and_nod():
    d = detector()
    seen = set()
    for dx in [0, 0.015, -0.015, 0.015, -0.015, 0.015]:
        seen |= d.update(frame(nose_dx=dx))
    assert "head_shake" in seen and "head_nod" not in seen
    d = detector()
    seen = set()
    for dy in [0, 0.01, -0.01, 0.01, -0.01, 0.01]:
        seen |= d.update(frame(nose_dy=dy))
    assert "head_nod" in seen and "head_shake" not in seen


def test_swings_counts_turns():
    assert swings([0, 1, 0, 1, 0], 0.5) == 3
    assert swings([0, 0.1, 0.2, 0.3], 0.5) == 0


def test_tally_keeps_markers_seen_in_enough_frames():
    tally = MarkerTally(share=0.4)
    for markers in [{"brows_raised"}] * 3 + [set()] * 2 + [{"head_nod"}]:
        tally.add(frozenset(markers))
    assert tally.take() == {"brows_raised"}
    assert tally.take() == frozenset()
