"""Try signs live with the ASL Citizen model: what it sees, and why a demo sign does or
doesn't count, so the cutoffs in config.yaml can be set from real signing.

    uv sync --extra camera
    uv run python tools/try_signs.py                  # q quits

Sign inside the green box (the signing space saved in setup), then rest your hands. Each
time the model runs (every `asl_citizen_stride` frames) the terminal gets a line:

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
    from recognition.camera import Camera
    from recognition.gating import SigningSpace
    from recognition.segmenter import Segmenter
    from tools.try_letters import draw
    from ui.server import UI_CONFIG

    config = load_config()
    space = SigningSpace.from_config(config)
    try:  # the position saved in the app's setup ("Save This Position")
        space = SigningSpace(**json.loads(UI_CONFIG.read_text())["signing_space"])
    except (OSError, KeyError, TypeError, ValueError):
        pass
    model = ASLCitizenModel(config)
    segmenter = Segmenter.from_config(config)
    demo = sorted({display(model.glosses[i]) for i in model.allowed})
    print(f"Demo signs: {', '.join(demo)}")
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
            prediction = None
            if frame.hands_in_signing_space:
                ran = (
                    model._since_run + 1 >= model.stride
                    and len(model.frames) + 1 >= model.min_window
                )
                prediction = model.predict(frame)
                if ran:
                    frames = list(model.frames)
                    taken = (
                        f"{prediction.gloss} {prediction.confidence:.2f}"
                        if prediction
                        else "nothing"
                    )
                    line = f"takes: {taken}"
                    print(f"{taken:<14} as seen: {explain(frames, False)}", flush=True)
                    print(f"{'':<14} mirrored: {explain(frames, True)}", flush=True)
            event = segmenter.push(prediction)
            if event is not None:
                recognized.append(event.gloss)
                print(f"==> recognized {event.gloss}", flush=True)
            if not draw(cv2, frame, space, [line, "", " ".join(recognized[-6:]) or "-"]):
                break
    finally:
        camera.close()
        cv2.destroyAllWindows()
    print(f"Recognized: {' '.join(recognized) or '(nothing)'}")


if __name__ == "__main__":
    main()
