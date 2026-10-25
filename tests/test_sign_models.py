"""The real sign classifiers: the Kaggle isolated-sign model and recorded custom signs."""

import numpy as np
import pytest

from recognition.custom_signs import CustomSignLibrary, CustomSignModel, frame_features
from recognition.isolated import LANDMARKS, IsolatedSignModel, frame_array
from shared.config import Config, load_config
from shared.events import LandmarkFrame

POSE = tuple((0.5, 0.5, 0.0) for _ in range(11)) + ((0.6, 0.6, 0.0), (0.4, 0.6, 0.0))
POSE = POSE + tuple((0.5, 0.8, 0.0) for _ in range(20))


def hand(x, y, spread=0.02):
    return tuple((x + spread * (i % 5), y - spread * (i // 5), 0.0) for i in range(21))


def frame(x, y, ts, spread=0.02):
    return LandmarkFrame(
        right_hand=hand(x, y, spread), pose=POSE, face=((0.5, 0.3, 0.0),) * 478, ts=ts
    )


def test_frame_array_uses_the_competition_layout():
    a = frame_array(frame(0.3, 0.4, 0))
    assert a.shape == (LANDMARKS, 3)
    assert not np.isnan(a[:468]).any()  # face (iris points beyond 468 dropped)
    assert np.isnan(a[468:489]).all()  # no left hand
    assert not np.isnan(a[522:543]).any()  # right hand


class FakeRunner:
    def __init__(self):
        self.calls = 0

    def __call__(self, inputs):
        self.calls += 1
        logits = np.zeros(3)
        logits[1] = 5.0
        return {"outputs": logits}


def test_isolated_model_runs_every_few_frames_and_keeps_its_answer():
    config = Config(sections={"recognition": {"isolated_min_frames": 4, "isolated_stride": 2}})
    runner = FakeRunner()
    model = IsolatedSignModel(config, runner=runner, labels=["HELLO", "THANKYOU", "YES"])
    predictions = [model.predict(frame(0.5, 0.4, t / 30)) for t in range(10)]
    assert predictions[:3] == [None] * 3
    assert {p.gloss for p in predictions[3:]} == {"THANKYOU"}
    assert runner.calls == 4  # frames 4, 6, 8, 10
    # Hands left the signing space for a while: a fresh window.
    assert model.predict(frame(0.5, 0.4, 5.0)) is None


@pytest.fixture
def real_model():
    pytest.importorskip("ai_edge_litert")
    config = load_config()
    if not (config.path("recognition.isolated_model_dir") / "model.tflite").exists():
        pytest.skip("Kaggle model not downloaded (it downloads on first camera run)")
    return IsolatedSignModel(config)


def test_the_real_kaggle_model_loads_and_answers(real_model):
    window = np.stack([frame_array(frame(0.5, 0.4, t / 30)) for t in range(30)])
    top = real_model.top(window)
    assert len(real_model.labels) == 250 and "THANKYOU" in real_model.labels
    assert len(top) == 5 and 0 <= top[0][1] <= 1


def sweep(x0, x1, ts0, n=20, y=0.4, spread=0.02):
    return [frame(x0 + (x1 - x0) * i / (n - 1), y, ts0 + i / 30, spread) for i in range(n)]


@pytest.fixture
def library(tmp_path):
    lib = CustomSignLibrary(tmp_path / "custom")
    rng = np.random.default_rng(0)
    for _ in range(4):
        jitter = rng.normal(0, 0.01)
        lib.add("WW", sweep(0.3 + jitter, 0.7, 0))  # hand moves right
        lib.add("TITLE", sweep(0.5 + jitter, 0.5, 0, y=0.25, spread=0.05))  # high, still, open
    return lib


def test_library_saves_and_reloads_examples(library):
    again = CustomSignLibrary(library.folder)
    assert {g: len(c) for g, c in again.examples.items()} == {"TITLE": 4, "WW": 4}
    assert again.lengths["WW"] == 20


def test_custom_signs_match_their_own_movement_and_ignore_others(library):
    model = CustomSignModel(Config(), library=library)
    seen = [model.predict(f) for f in sweep(0.31, 0.69, 10)]
    assert seen[-1] is not None and seen[-1].gloss == "WW"

    model = CustomSignModel(Config(), library=library)
    other = [model.predict(f) for f in sweep(0.7, 0.3, 20, y=0.6, spread=0.0)]  # unlike either
    assert all(p is None for p in other)


def test_features_need_a_body():
    assert frame_features(LandmarkFrame(right_hand=hand(0.5, 0.5))) is None


def test_custom_signs_can_be_limited_to_the_ones_in_use(tmp_path):
    from recognition.custom_signs import CustomSignLibrary, CustomSignModel
    from shared.config import Config

    library = CustomSignLibrary(tmp_path)
    library.examples = {g: [np.zeros((24, 90))] for g in ("HELLO", "WAIT", "YES")}
    library.lengths = dict.fromkeys(library.examples, 20)
    config = Config(sections={"recognition": {"custom_signs": ["WAIT", True]}})  # True = YES
    model = CustomSignModel(config, library=library)
    assert set(model.library.examples) == {"WAIT", "YES"}
