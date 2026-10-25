"""Tune recognition on recorded takes of the demo script (tools/record_script.py).

    uv run python tools/tune_recognition.py                # every take in models/takes/
    uv run python tools/tune_recognition.py --details      # what each take came out as
    uv run python tools/tune_recognition.py --quick        # a smaller sweep

Each take is replayed through the real classifiers (custom signs, then the main sign model:
ASL Citizen when `recognition.sign_models` has it and it's set up, else the Kaggle model)
and the segmenter, the way the camera recognizer runs them, for every combination of:

    <model>_window, <model>_stride        (the model's window: re-runs the model)
    <model>_floor, confidence_threshold, min_frames, control_min_frames   (cheap)

(<model> is asl_citizen or isolated), and the signs each take produced are compared with
the glosses it should give (an edit distance: a missing, extra or wrong sign is one error).
Signs no model can know (not in the model's signs and not recorded as a custom sign) are
listed and left out of the score: record them with tools/record_signs.py. Fingerspelled
letters in a take aren't scored. The best settings are printed as config.yaml lines.

Uses the signing space saved in setup (Save This Position), like the app.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recognition.base import FrameClassifier, Prediction  # noqa: E402
from recognition.gating import SigningSpace  # noqa: E402
from recognition.mock import parse_line  # noqa: E402
from recognition.replay import frame_from_json  # noqa: E402
from recognition.segmenter import Segmenter  # noqa: E402
from shared.config import Config, load_config  # noqa: E402
from shared.events import LandmarkFrame, SignEvent  # noqa: E402

# Glosses that count as the same sign: our gloss -> what a model may call it.
EQUIVALENT: dict[str, set[str]] = {
    "NICE": {"CLEAN"},  # the same sign (Lifeprint); the Kaggle model knows it as CLEAN
    "THANK-YOU": {"THANKYOU"},
    "MY": {"MINEMY"},
    "SEND": {"FINISH"},
    "MEET-YOU": {"MEET"},  # ASL Citizen has the plain form
}
PARAMS = ("window", "stride", "floor", "threshold", "min_frames", "control_min_frames")
FULL = {
    "window": [32, 48, 64],
    "stride": [2, 4],
    "floor": [0.2, 0.3, 0.4, 0.5],
    "threshold": [0.4, 0.5, 0.6, 0.7],
    "min_frames": [3, 5, 8],
    "control_min_frames": [0, 8, 15],
}
# ASL Citizen's training clips are whole one-sign videos (~2-4 s): longer windows.
ASL_CITIZEN = {"window": [45, 60, 90], "stride": [4], "floor": [0.4, 0.5, 0.6, 0.7]}
ASL_CITIZEN_QUICK = {"window": [60], "stride": [4], "floor": [0.4, 0.5, 0.6]}
QUICK = {
    "window": [48],
    "stride": [4],
    "floor": [0.2, 0.3, 0.4],
    "threshold": [0.4, 0.5, 0.6],
    "min_frames": [3, 5],
    "control_min_frames": [0, 10],
}


@dataclass
class Take:
    name: str
    phrase: str
    frames: list[LandmarkFrame]

    @property
    def expected(self) -> list[str]:
        return expected_glosses(self.phrase)


@dataclass
class Result:
    params: dict[str, Any]
    errors: int = 0  # over the signs a model can know
    perfect: int = 0  # takes that came out exactly right
    got: dict[str, list[str]] = field(default_factory=dict)


def expected_glosses(phrase: str) -> list[str]:
    """The signs a phrase should give, as SignEvent glosses (FINISH is SEND)."""
    return [e.gloss for e in parse_line(phrase) if isinstance(e, SignEvent)]


def same(expected: str, got: str) -> bool:
    return got == expected or got in EQUIVALENT.get(expected, ())


def errors(expected: Sequence[str], got: Sequence[str]) -> int:
    """Edit distance: each missing, extra or wrong sign is one error."""
    row = list(range(len(got) + 1))
    for i, e in enumerate(expected, 1):
        prev, row[0] = row[0], i
        for j, g in enumerate(got, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (not same(e, g)))
    return row[-1]


def knowable(gloss: str, vocabulary: set[str]) -> bool:
    return gloss in vocabulary or bool(EQUIVALENT.get(gloss, set()) & vocabulary)


def load_takes(folder: Path) -> list[Take]:
    from tools.record_script import load_manifest

    takes = []
    for name, phrase in load_manifest(folder).items():
        path = folder / name
        if not path.exists():
            continue
        frames = []
        for i, line in enumerate(path.read_text().splitlines()):
            if line.strip():
                data = json.loads(line)
                t = float(data.get("t", i / 30))
                frames.append(replace(frame_from_json(data), ts=t))
        takes.append(Take(name, phrase, frames))
    return takes


def signing_space(config: Config) -> SigningSpace:
    """The space saved in setup (ui.json), else config.yaml's."""
    from ui.server import UI_CONFIG

    try:
        box = json.loads(UI_CONFIG.read_text()).get("signing_space")
        if isinstance(box, dict):
            return SigningSpace(**{k: float(v) for k, v in box.items()})
    except (OSError, ValueError, TypeError):
        pass
    return SigningSpace.from_config(config)


def with_recognition(config: Config, **values: Any) -> Config:
    section = {**config.section("recognition"), **values}
    return replace(config, sections={**config.sections, "recognition": section})


def main_model(config: Config) -> str:
    """The config prefix of the main sign model: asl_citizen (if used and set up) or isolated."""
    models = config.get("recognition.sign_models", ["custom", "kaggle"]) or []
    folder = config.path("recognition.asl_citizen_dir", "models/asl_citizen")
    return (
        "asl_citizen"
        if "asl_citizen" in models and (folder / "stgcn.onnx").exists()
        else "isolated"
    )


def model_values(config: Config, window: int, stride: int, floor: float) -> dict[str, Any]:
    prefix = main_model(config)
    return {f"{prefix}_window": window, f"{prefix}_stride": stride, f"{prefix}_floor": floor}


# A factory gives (custom-sign classifier, main classifier) for a config; the main one
# must report every prediction (floor 0), so the floor can be swept afterwards.
Factory = Callable[[Config], tuple[FrameClassifier | None, FrameClassifier]]


def real_classifiers(config: Config) -> tuple[FrameClassifier | None, FrameClassifier]:
    from recognition.custom_signs import CustomSignModel

    custom = CustomSignModel(config)
    if main_model(config) == "asl_citizen":
        from recognition.asl_citizen import ASLCitizenModel

        model: FrameClassifier = ASLCitizenModel(config)
    else:
        from recognition.isolated import IsolatedSignModel

        model = IsolatedSignModel(config)
    return (custom if custom.library.examples else None), model


def raw_predictions(
    take: Take, config: Config, space: SigningSpace, factory: Factory
) -> list[tuple[Prediction | None, Prediction | None] | None]:
    """Per frame: (custom-sign answer, main model's answer), or None when the hands are down."""
    custom, isolated = factory(config)
    out: list[tuple[Prediction | None, Prediction | None] | None] = []
    for raw in take.frames:
        frame = space.apply(raw)
        if not frame.hands_in_signing_space:
            out.append(None)
            continue
        c = custom.predict(frame) if custom is not None else None
        out.append((c, isolated.predict(frame)))
    return out


def segment(raw, floor: float, threshold: float, min_frames: int, control: int) -> list[str]:
    segmenter = Segmenter(min_frames, threshold, control or None)
    glosses = []
    for answers in raw:
        prediction = None
        if answers is not None:
            custom, isolated = answers
            if custom is not None:
                prediction = custom
            elif isolated is not None and isolated.confidence >= floor:
                prediction = isolated
        event = segmenter.push(prediction)
        if event is not None:
            glosses.append(event.gloss)
    return glosses


def sweep(
    takes: list[Take],
    config: Config,
    grid: dict[str, list[Any]],
    vocabulary: set[str],
    factory: Factory = real_classifiers,
    space: SigningSpace | None = None,
    progress: Callable[[str], None] = lambda _: None,
) -> list[Result]:
    space = space or signing_space(config)
    results = []
    for window, stride in itertools.product(grid["window"], grid["stride"]):
        progress(f"window {window}, stride {stride}")
        model_config = with_recognition(config, **model_values(config, window, stride, 0.0))
        raw = {t.name: raw_predictions(t, model_config, space, factory) for t in takes}
        for floor, threshold, min_frames, control in itertools.product(
            grid["floor"], grid["threshold"], grid["min_frames"], grid["control_min_frames"]
        ):
            values = (window, stride, floor, threshold, min_frames, control)
            params = dict(zip(PARAMS, values, strict=True))
            result = Result(params)
            for take in takes:
                got = segment(raw[take.name], floor, threshold, min_frames, control)
                result.got[take.name] = got
                # Signs no model knows can't be found; a false sign in their place still counts.
                want = [g for g in take.expected if knowable(g, vocabulary)]
                result.errors += errors(want, got)
                result.perfect += errors(take.expected, got) == 0
            results.append(result)
    current = current_params(config)
    results.sort(key=lambda r: (r.errors, -r.perfect, changed(r.params, current)))
    return results


def current_params(config: Config) -> dict[str, Any]:
    get = lambda key, default: config.get(f"recognition.{key}", default)  # noqa: E731
    prefix = main_model(config)
    defaults = (60, 4, 0.5) if prefix == "asl_citizen" else (48, 4, 0.3)
    return {
        "window": int(get(f"{prefix}_window", defaults[0])),
        "stride": int(get(f"{prefix}_stride", defaults[1])),
        "floor": float(get(f"{prefix}_floor", defaults[2])),
        "threshold": float(get("confidence_threshold", 0.6)),
        "min_frames": int(get("min_frames", 5)),
        "control_min_frames": int(get("control_min_frames", 0)),
    }


def changed(params: dict[str, Any], current: dict[str, Any]) -> int:
    return sum(params[k] != current[k] for k in PARAMS)


def vocabulary(config: Config) -> set[str]:
    """Every gloss the models can produce: the main model's signs, the custom signs, the
    controls."""
    from recognition.custom_signs import CustomSignLibrary

    if main_model(config) == "asl_citizen":
        from recognition.asl_citizen import DEMO_SIGNS, display

        folder = config.path("recognition.asl_citizen_dir", "models/asl_citizen")
        known = {display(g) for g in (folder / "glosses.txt").read_text().split()}
        wanted = config.get("recognition.asl_citizen_signs", DEMO_SIGNS) or known
        flags = {True: "YES", False: "NO"}
        words = {display(flags.get(w, w) if isinstance(w, bool) else str(w)) for w in wanted}
        words &= known
    else:
        path = config.path("recognition.isolated_model_dir", "models/islr")
        index = path / "sign_to_prediction_index_map.json"
        words = {w.upper() for w in json.loads(index.read_text())} if index.exists() else set()
    custom = CustomSignLibrary(config.path("recognition.custom_signs_dir", "models/custom_signs"))
    return words | set(custom.examples) | {"SEND", "YES", "NO"}


def config_lines(params: dict[str, Any], prefix: str = "isolated") -> str:
    return "\n".join(
        [
            "recognition:",
            f"  {prefix}_window: {params['window']}",
            f"  {prefix}_stride: {params['stride']}",
            f"  {prefix}_floor: {params['floor']}",
            f"  confidence_threshold: {params['threshold']}",
            f"  min_frames: {params['min_frames']}",
            f"  control_min_frames: {params['control_min_frames']}",
        ]
    )


def seen(raw: Iterable, top: int = 6) -> str:
    """The models' most confident guesses during a take (for spotting confusions)."""
    best: dict[str, float] = {}
    for answers in raw:
        if answers is None:
            continue
        for p in answers:
            if p is not None and p.confidence > best.get(p.gloss, 0.0):
                best[p.gloss] = p.confidence
    ranked = sorted(best.items(), key=lambda kv: -kv[1])[:top]
    return ", ".join(f"{g} {c:.2f}" for g, c in ranked) or "nothing"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--takes", type=Path, help="folder (default models/takes)")
    parser.add_argument("--quick", action="store_true", help="a smaller sweep")
    parser.add_argument("--details", action="store_true", help="every take, best settings")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    from tools.record_script import TAKES_DIR

    config = load_config()
    takes = load_takes(args.takes or TAKES_DIR)
    if not takes:
        print("No takes yet: record some with tools/record_script.py")
        return
    vocab = vocabulary(config)
    unknown = sorted({g for t in takes for g in t.expected if not knowable(g, vocab)})
    print(f"{len(takes)} takes of {len({t.phrase for t in takes})} phrases")
    if unknown:
        print(f"No model knows yet (record with tools/record_signs.py): {', '.join(unknown)}")
    grid = QUICK if args.quick else FULL
    if main_model(config) == "asl_citizen":
        grid = {**grid, **(ASL_CITIZEN_QUICK if args.quick else ASL_CITIZEN)}
    print(f"Main sign model: {main_model(config)}")
    results = sweep(takes, config, grid, vocab, progress=lambda s: print(f"  running {s}"))
    total = sum(len([g for g in t.expected if knowable(g, vocab)]) for t in takes)
    current = current_params(config)
    now = next((r for r in results if r.params == current), None)

    print(f"\nBest settings ({total} knowable signs over all takes):")
    for r in results[: args.top]:
        p = r.params
        print(
            f"  {r.errors:3d} errors, {r.perfect:2d}/{len(takes)} takes right  "
            f"window {p['window']} stride {p['stride']} floor {p['floor']} "
            f"threshold {p['threshold']} min_frames {p['min_frames']} "
            f"control {p['control_min_frames'] or '2x'}"
        )
    if now is not None:
        print(f"  current config.yaml: {now.errors} errors, {now.perfect}/{len(takes)} right")
    best = results[0]
    print("\nIn config.yaml:\n" + config_lines(best.params, main_model(config)))

    if args.details:
        p = best.params
        model_config = with_recognition(
            config, **model_values(config, p["window"], p["stride"], 0.0)
        )
        space = signing_space(config)
        print("\nEach take with the best settings:")
        for take in takes:
            got = best.got[take.name]
            mark = "ok" if errors(take.expected, got) == 0 else "  "
            print(f"  {mark} {take.name}: want {' '.join(take.expected)} | got {' '.join(got)}")
            raw = raw_predictions(take, model_config, space, real_classifiers)
            print(f"       saw: {seen(raw)}")


if __name__ == "__main__":
    main()
