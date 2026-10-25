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


WINDOW = Config(sections={"recognition": {"custom_mode": "window"}})


def test_one_sign_per_raise_of_the_hands(library):
    model = CustomSignModel(Config(), library=library)
    assert model.state(hands_up=False) == "idle"
    signed = sweep(0.31, 0.69, 10)
    out = [model.predict(f) for f in signed]
    found = [p for p in out if p is not None]
    assert [p.gloss for p in found] == ["WW"]  # once, while the hands are still up
    assert found[0].confidence >= 0.6 and model.state(hands_up=True) == "detected"
    more = sweep(0.31, 0.69, signed[-1].ts + 1 / 30)  # signing on, hands still up
    assert all(model.predict(f) is None for f in more)  # locked: no more
    end = more[-1].ts
    assert model.end_segment(end + 0.1) is None and model.state(hands_up=False) == "detected"
    assert model.end_segment(end + 0.5) is None  # down long enough: unlocked
    assert model.state(hands_up=False) == "idle"
    again = [model.predict(f) for f in sweep(0.31, 0.69, end + 1)]
    assert [p.gloss for p in again if p] == ["WW"]  # the next raise is a new sign


def test_a_sign_that_never_matched_gets_a_last_try_when_the_hands_drop(library):
    model = CustomSignModel(
        Config(sections={"recognition": {"custom_early_fraction": 5}}), library=library
    )
    signed = sweep(0.31, 0.69, 10)  # early matches need 5x the length: none happen
    assert all(model.predict(f) is None for f in signed)
    seen = model.end_segment(signed[-1].ts + 0.5)
    assert seen is not None and seen.gloss == "WW"

    for f in sweep(0.7, 0.3, 20, 20, y=0.6, spread=0.0):  # unlike either sign
        assert model.predict(f) is None
    assert model.end_segment(30) is None


def test_custom_signs_in_window_mode_match_while_signing(library):
    model = CustomSignModel(WINDOW, library=library)
    seen = [model.predict(f) for f in sweep(0.31, 0.69, 10)]
    assert seen[-1] is not None and seen[-1].gloss == "WW"

    model = CustomSignModel(WINDOW, library=library)
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


async def test_the_pipeline_emits_a_custom_sign_when_the_hands_drop(library):
    import asyncio

    from recognition.base import FrameRecognizer
    from shared.bus import Bus
    from shared.events import SignEvent

    rest = [LandmarkFrame(pose=POSE, ts=1.0 + i / 30) for i in range(20)]  # hands down

    class Scripted(FrameRecognizer):
        name = "scripted"

        async def frames(self):
            for f in sweep(0.31, 0.69, 0.0) + rest:
                yield f
            await asyncio.sleep(0)

        def classifiers(self):
            return [CustomSignModel(Config(), library=library)]

    bus = Bus()
    signs = bus.subscribe(SignEvent)
    recognizer = Scripted(bus, Config())
    await recognizer.start()
    await asyncio.wait_for(recognizer._task, 5)
    assert [signs.get_nowait().gloss for _ in range(signs.queue.qsize())] == ["WW"]


def test_a_raise_spent_fingerspelling_gives_no_sign(library):
    model = CustomSignModel(Config(), library=library)
    signed = sweep(0.31, 0.69, 10)
    model.predict(signed[0])
    model.spelled()  # the letter reader saw a letter held
    assert all(model.predict(f) is None for f in signed[1:])  # not WW: it's spelling
    assert model.end_segment(signed[-1].ts + 0.5) is None  # and no last try at the drop
    again = [model.predict(f) for f in sweep(0.31, 0.69, 12)]
    assert [p.gloss for p in again if p] == ["WW"]  # the next raise is a sign again
