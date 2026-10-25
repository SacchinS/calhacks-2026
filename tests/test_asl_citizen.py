"""The ASL Citizen sign model (recognition/asl_citizen.py): the input matches the training
code's preprocessing, the vocabulary limit and "nothing" checks, and model selection. The
real model runs only when tools/setup_asl_citizen.py has been run (else skipped)."""

import numpy as np
import pytest

import recognition.base as base
from recognition.asl_citizen import (
    FRAMES,
    KEYPOINTS,
    ASLCitizenModel,
    clip_input,
    frame_points,
)
from shared.config import Config, load_config
from shared.events import LandmarkFrame

RNG = np.random.default_rng(0)


def pose(shift=0.0):
    points = [(0.5 + shift, 0.3, 0.0)] * 33
    points[11], points[12] = (0.62 + shift, 0.5, 0.0), (0.38 + shift, 0.5, 0.0)
    points[2], points[5] = (0.52 + shift, 0.28, 0.0), (0.48 + shift, 0.28, 0.0)
    return tuple(points)


def hand(x):
    return tuple((x + 0.005 * i, 0.4 - 0.004 * i, 0.0) for i in range(21))


def training_preprocessing(data0):
    """ST-GCN/asl_citizen_dataset_pose.py __getitem__, from `length = ...` on, verbatim
    except for the torch tensor at the end. data0: (T, 75, 2) pose, right hand, left hand
    (the order pose.py saves)."""

    def their_downsample(frames, max_frames):
        length = frames.shape[0]
        increment = max_frames / length
        if increment > 1.0:
            increment = 1.0
        curr_increment = 0
        curr_frame = 0
        new_frames = []
        for f in frames:
            curr_increment += increment
            if curr_increment > curr_frame:
                curr_frame += 1
                new_frames.append(f)
        if len(new_frames) > max_frames:
            new_frames = new_frames[:max_frames]
        return np.array(new_frames)

    max_frames = 128
    length = data0.shape[0]
    if length > max_frames:
        data0 = their_downsample(data0, max_frames)
    if length < max_frames:
        data0 = np.pad(data0, ((0, max_frames - length), (0, 0), (0, 0)))
    shoulder_l = data0[:, 11, :]
    shoulder_r = data0[:, 12, :]
    center = np.zeros(2)
    for i in range(len(shoulder_l)):
        center_i = (shoulder_r[i] + shoulder_l[i]) / 2
        center = center + center_i
    center = center / shoulder_l.shape[0]
    mean_dist = np.mean(np.sqrt(((shoulder_l - shoulder_r) ** 2).sum(-1)))
    if mean_dist != 0:
        scale = 1.0 / mean_dist
        data0 = data0 - center
        data0 = data0 * scale
    data0 = data0[:, 0:75, :]
    posedata = data0[:, 0:33, :]
    rhdata = data0[:, 33:54, :]
    lhdata = data0[:, 54:, :]
    data = np.concatenate([posedata, lhdata, rhdata], axis=1)
    data = data[:, KEYPOINTS, :]
    return np.transpose(data, (2, 0, 1))


def as_saved(frames):
    """Our frames in pose.py's saved order: pose, right hand, left hand (x, y)."""
    out = np.zeros((len(frames), 75, 2))
    for t, f in enumerate(frames):
        out[t, :33] = np.asarray(f.pose)[:, :2]
        if f.right_hand:
            out[t, 33:54] = np.asarray(f.right_hand)[:, :2]
        if f.left_hand:
            out[t, 54:75] = np.asarray(f.left_hand)[:, :2]
    return out


@pytest.mark.parametrize("length", [40, 128, 200])
def test_input_matches_the_training_code(length):
    frames = []
    for t in range(length):
        jitter = RNG.normal(0, 0.01)
        frames.append(
            LandmarkFrame(
                pose=pose(jitter),
                right_hand=hand(0.4 + jitter) if t % 7 else (),  # sometimes not seen
                left_hand=hand(0.6),
            )
        )
    ours = clip_input([frame_points(f) for f in frames])
    assert ours.shape == (1, 2, FRAMES, 27)
    assert np.allclose(ours[0], training_preprocessing(as_saved(frames)), atol=1e-5)


def test_a_mirror_swaps_left_and_right():
    frame = LandmarkFrame(pose=pose(), left_hand=hand(0.6), right_hand=hand(0.3))
    plain, mirrored = frame_points(frame), frame_points(frame, mirrored=True)
    assert np.allclose(mirrored[33:54, 0], 1 - plain[54:75, 0])  # the right hand, now on the left
    assert np.allclose(mirrored[11], [1 - plain[12, 0], plain[12, 1]])  # shoulders swap


GLOSSES = ["BOW3", "HELLO", "HOW1", "HOW2", "MEET", "WELCOME2", "YES"]


def model(logits, **settings):
    config = Config(sections={"recognition": {"asl_citizen_top_k": 3, **settings}})
    return ASLCitizenModel(config, run=lambda x: np.asarray(logits)[None], glosses=GLOSSES)


FRAMES_UP = [LandmarkFrame(pose=pose(), right_hand=hand(0.4), ts=t / 30) for t in range(20)]


def test_only_the_demo_signs_and_only_when_the_model_rates_them():
    meet = model([0, 1, 0, 0, 3, 2.5, 0], asl_citizen_signs=["HELLO", "MEET", "YES"])
    assert meet.classify(FRAMES_UP).gloss == "MEET"  # WELCOME2 is likelier but not a demo sign
    nothing = model([5, 0, 0, 0, 0.5, 4, 0], asl_citizen_signs=["MEET"])  # MEET isn't in the top 3
    assert nothing.classify(FRAMES_UP) is None
    weak = model([0, 0, 0, 0, 1, 0, 0], asl_citizen_signs=["MEET"], asl_citizen_min_prob=0.5)
    assert weak.classify(FRAMES_UP) is None  # top of the list, but only 25% of the whole model


def test_variants_count_as_one_sign():
    how = model([0, 1, 2, 2, 0, 0, 0], asl_citizen_signs=["HOW", "HELLO"])
    prediction = how.classify(FRAMES_UP)
    assert prediction.gloss == "HOW" and prediction.confidence > 0.8  # HOW1 + HOW2


def test_sign_models_follow_the_config_and_fall_back_to_kaggle(monkeypatch, tmp_path):
    class Kaggle:
        def __init__(self, config):
            pass

    monkeypatch.setattr("recognition.isolated.IsolatedSignModel", Kaggle)
    config = Config(
        sections={"recognition": {"sign_models": ["asl_citizen"], "asl_citizen_dir": str(tmp_path)}}
    )
    (only,) = base.sign_classifiers(config)  # not set up here: Kaggle stands in
    assert isinstance(only, Kaggle)
    with pytest.raises(ValueError):
        base.sign_classifiers(Config(sections={"recognition": {"sign_models": ["nope"]}}))


def test_the_real_model_ignores_a_still_hand():
    config = load_config()
    if not (config.path("recognition.asl_citizen_dir") / "stgcn.onnx").exists():
        pytest.skip("ASL Citizen isn't set up (tools/setup_asl_citizen.py)")
    pytest.importorskip("onnxruntime")
    real = ASLCitizenModel(config)
    assert {real.glosses[i] for i in real.allowed} >= {"HELLO", "NICE", "MEET", "YES"}
    assert real.classify(FRAMES_UP) is None
