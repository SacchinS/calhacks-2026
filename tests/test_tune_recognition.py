"""The recognition tuner (tools/tune_recognition.py) and the take recorder's files, without a
webcam: takes are made from the labeled sample fixture and classified from their labels."""

from pathlib import Path

from recognition.base import FrameClassifier, Prediction
from recognition.gating import SigningSpace
from recognition.replay import read_fixture
from shared.config import load_config
from tools.record_script import load_manifest, save_take
from tools.tune_recognition import (
    QUICK,
    Take,
    errors,
    expected_glosses,
    knowable,
    load_takes,
    sweep,
)

SAMPLE = Path("fixtures/landmarks_sample.jsonl")


def test_expected_glosses_follow_the_mock_sign_syntax():
    assert expected_glosses("TITLE /\\ RED") == ["TITLE", "RED"]
    assert expected_glosses("TOMORROW MORNING, YOU-REMIND-ME BUY MILK") == [
        "TOMORROW",
        "MORNING",
        "YOU-REMIND-ME",
        "BUY",
        "MILK",
    ]
    assert expected_glosses("FINISH") == ["SEND"]  # FINISH is the SEND control sign


def test_errors_count_missing_extra_and_wrong_signs_and_allow_equivalents():
    assert errors(["HELLO", "NICE", "MEET-YOU"], ["HELLO", "CLEAN", "MEET-YOU"]) == 0
    assert errors(["THANK-YOU"], ["THANKYOU"]) == 0
    assert errors(["FOOD", "STORE", "MAKE"], ["FOOD", "MAKE"]) == 1  # missing
    assert errors(["FOOD", "STORE", "MAKE"], ["FOOD", "STORE", "COFFEE"]) == 1  # wrong
    assert errors(["RED"], ["RED", "RED"]) == 1  # extra
    assert errors([], ["RED"]) == 1


def test_signs_no_model_knows_are_found():
    vocab = {"HELLO", "CLEAN", "SEND"}
    assert knowable("NICE", vocab)  # as CLEAN
    assert knowable("SEND", vocab)
    assert not knowable("MEET-YOU", vocab)


def test_takes_round_trip_with_their_timing(tmp_path):
    frames = list(read_fixture(SAMPLE))
    path = save_take("MAKE RED", frames, folder=tmp_path)
    save_take("MAKE RED", frames, folder=tmp_path)
    assert load_manifest(tmp_path) == {path.name: "MAKE RED", "make-red-02.jsonl": "MAKE RED"}
    (take, _) = load_takes(tmp_path)
    assert take.phrase == "MAKE RED" and len(take.frames) == len(frames)
    assert take.frames[0].ts == 0.0 and take.frames[-1].ts > 0


class LabelClassifier(FrameClassifier):
    """Says the frame's label: a perfect model, to check the sweep and the scoring."""

    def predict(self, frame):
        if not frame.label:
            return None
        if frame.label.startswith("#"):
            return Prediction(frame.label[1:], 0.55, "fingerspell")
        return Prediction(frame.label, 0.55, "isolated")


def test_sweep_finds_settings_that_recognize_every_sign():
    config = load_config()
    take = Take("sample", "MAKE #title RED FINISH YES", list(read_fixture(SAMPLE)))
    vocab = {"MAKE", "TITLE", "RED", "SEND", "YES"}
    results = sweep(
        [take],
        config,
        QUICK,
        vocab,
        factory=lambda cfg: (None, LabelClassifier()),
        space=SigningSpace.from_config(config),
    )
    best, worst = results[0], results[-1]
    assert best.errors == 0 and best.perfect == 1
    assert best.got["sample"] == ["MAKE", "TITLE", "RED", "SEND", "YES"]
    assert best.params["threshold"] <= 0.55  # the model's confidence
    assert worst.errors > 0  # a threshold above 0.55 finds nothing


def test_unknown_signs_dont_count_but_false_signs_do():
    config = load_config()
    take = Take("sample", "MAKE #title RED FINISH YES WW", list(read_fixture(SAMPLE)))
    vocab = {"MAKE", "TITLE", "RED", "SEND", "YES"}  # nobody has recorded WW
    best = sweep(
        [take],
        config,
        QUICK,
        vocab,
        factory=lambda cfg: (None, LabelClassifier()),
        space=SigningSpace.from_config(config),
    )[0]
    assert best.errors == 0  # WW can't be recognized yet, so it isn't held against these
    assert best.perfect == 0  # but the take isn't fully right
