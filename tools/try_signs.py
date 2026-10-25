"""Try signs live: what the app would recognize (your recorded custom signs first, then
the ASL Citizen model), and why an ASL Citizen demo sign does or doesn't count, so the
cutoffs in config.yaml can be set from real signing.

    uv sync --extra camera
    uv run python tools/try_signs.py                  # q quits

One sign per raise of the hands, as in the app. The box (the signing space saved in setup)
is gray with your hands down, yellow while you sign, and green once the sign is recognized;
then drop your hands until it's gray before the next sign. The terminal shows each sign
that came out, or for one that didn't, its nearest recorded sign, the distance, the limit
and the runner-up when you drop your hands. With ASL Citizen on
(`recognition.sign_models`), each time that model runs (every `asl_citizen_stride`
frames) the terminal gets a line:

    HELLO 0.83 | rank, share of the whole model for each demo sign | top 5 of all 2,731

both as the camera sees you and mirrored. The first part is what the app would take (or
why nothing counts: not in the top `asl_citizen_top_k`, under `asl_citizen_min_prob`, or
under `asl_citizen_floor` among the demo signs). Signs the app would recognize, after the
segmenter, show in the window. Nothing is saved.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import load_config  # noqa: E402


def main() -> None:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    ).parse_args()  # --help prints this, without opening the camera

    import cv2
    import numpy as np

    from recognition.asl_citizen import ASLCitizenModel, display
    from recognition.base import make_sign_event
    from recognition.camera import Camera
    from recognition.custom_signs import CustomSignModel
    from recognition.gating import SigningSpace
    from recognition.segmenter import Segmenter
    from tools.try_letters import draw
    from ui.server import BOX_BGR, UI_CONFIG

    config = load_config()
    space = SigningSpace.from_config(config)
    try:  # the position saved in the app's setup ("Save This Position")
        space = SigningSpace(**json.loads(UI_CONFIG.read_text())["signing_space"])
    except (OSError, KeyError, TypeError, ValueError):
        pass
    uses_asl = "asl_citizen" in (config.get("recognition.sign_models", []) or [])
    model = ASLCitizenModel(config) if uses_asl else None  # off: custom signs only
    custom = CustomSignModel(config)
    print(f"Custom signs: {', '.join(sorted(custom.library.examples)) or '(none recorded)'}")
    segmenter = Segmenter.from_config(config)
    if model is not None:
        demo = sorted({display(model.glosses[i]) for i in model.allowed})
        print(f"ASL Citizen signs: {', '.join(demo)}")
        print(f"Cutoffs: top {model.top_k}, min_prob {model.min_prob}, floor {model.floor}\n")

    def explain(frames, mirrored: bool) -> str:
        probs = model.scores(frames, mirrored)
        order = np.argsort(probs)[::-1]
        rank = {int(i): r + 1 for r, i in enumerate(order)}
        signs: dict[str, tuple[int, float]] = {}
        for i in model.allowed:
            name = display(model.glosses[i])
            best = signs.get(name)
            if best is None or rank[i] < best[0]:
                signs[name] = (rank[i], float(probs[i]))
        top5 = " ".join(f"{model.glosses[i]} {probs[i]:.0%}" for i in order[:5])
        mine = " ".join(
            f"{n} #{r} {p:.0%}" for n, (r, p) in sorted(signs.items(), key=lambda s: s[1][0])
        )
        return f"{mine}  ||  {top5}"

    recognized: list[str] = []
    line = "sign inside the box"
    camera = Camera(config)
    try:
        while True:
            frame = camera.read()
            if frame is None:
                continue
            frame = space.apply(frame)
            prediction = mine = None
            if frame.hands_in_signing_space:
                ran = model is not None and (
                    model._since_run + 1 >= model.stride
                    and len(model.frames) + 1 >= model.min_window
                )
                clip = list(custom.segment) + [frame]
                mine = custom.predict(frame)  # a whole sign, as soon as it clearly matches
                theirs = model.predict(frame) if model is not None else None
                prediction = theirs if mine is None else None
                if mine is not None:
                    g, d, other = custom.segment_match(clip)
                    print(
                        f"sign of {len(clip)} frames -> {mine.gloss} (distance {d:.2f}, limit "
                        f"{custom.limit:.2f}, runner-up {other:.2f})",
                        flush=True,
                    )
                    line = f"{mine.gloss} {mine.confidence:.2f}: drop your hands for the next sign"
                if ran:
                    frames = list(model.frames)
                    taken = f"{theirs.gloss} {theirs.confidence:.2f}" if theirs else "nothing"
                    if mine is None:
                        line = f"asl citizen: {taken}"
                    print(f"{taken:<14} as seen: {explain(frames, False)}", flush=True)
                    print(f"{'':<14} mirrored: {explain(frames, True)}", flush=True)
            event = segmenter.push(prediction)
            if frame.hands_in_signing_space and mine is not None:
                event = make_sign_event(mine.gloss, mine.confidence)
            if not frame.hands_in_signing_space:
                clip = list(custom.segment)
                whole = custom.end_segment(frame.ts)
                if clip and not custom.segment:  # dropped without a match: the last try
                    match = custom.segment_match(clip)
                    if match is not None:
                        g, d, other = match
                        verdict = f"-> {whole.gloss}" if whole else "no sign"
                        print(
                            f"sign of {len(clip)} frames, hands down: nearest {g:9} {d:.2f} "
                            f"(limit {custom.limit:.2f}, runner-up {other:.2f}) {verdict}",
                            flush=True,
                        )
                    if whole is not None:
                        event = event or make_sign_event(whole.gloss, whole.confidence)
                state = custom.state(False)
                if state == "idle":
                    line = "sign inside the box"
            if event is not None:
                recognized.append(event.gloss)
                print(f"==> recognized {event.gloss}", flush=True)
            state = custom.state(frame.hands_in_signing_space)
            box = BOX_BGR[state]
            if not draw(cv2, frame, space, [line, "", " ".join(recognized[-6:]) or "-"], box):
                break
    finally:
        camera.close()
        cv2.destroyAllWindows()
    print(f"Recognized: {' '.join(recognized) or '(nothing)'}")


if __name__ == "__main__":
    main()
