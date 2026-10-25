"""Record examples of a custom sign from the webcam (recognition/custom_signs.py).

    uv sync --extra camera
    uv run python tools/record_signs.py WW --takes 5      # 5 examples of WW
    uv run python tools/record_signs.py --list            # what's recorded
    uv run python tools/record_signs.py --check           # how well the examples separate

For each take: a window shows the camera; rest your hands below the green box, wait for
"GO", sign once, then drop your hands below the box. One sign per take: a take that runs
into the 4 s limit (hands still in the box, or the sign repeated) or is under 8 frames is
thrown away and redone, since live signs are matched the same way, hands-in to hands-out.
The box is gray with your hands down and yellow while recording.

Examples go to models/custom_signs/<GLOSS>/ (gitignored): NN.npz is what the matcher uses;
NN.jsonl is the take's raw landmarks with half a second of rest on each side (the replay
format, so takes can be replayed through the other sign models). Record only teammates who
agree, and learn each sign from a Deaf signer or the linked source videos first.
Press q to quit early.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recognition.custom_signs import CustomSignLibrary, distance  # noqa: E402
from shared.config import load_config  # noqa: E402

MAX_SECONDS = 4.0  # longest take: one that runs this long is redone (it's several signs)
MIN_FRAMES = 8  # shorter is a hand brushing the box, not a sign: redone
SIGNING_BGR = (0, 210, 255)  # the box while a sign is being made (yellow)
END_GAP = 0.35  # hands out of the signing space this long ends the take


def library() -> CustomSignLibrary:
    return CustomSignLibrary(
        load_config().path("recognition.custom_signs_dir", "models/custom_signs")
    )


def show(cv2, frame, text: str, color=(255, 255, 255), space=None) -> bool:
    """Draw the mirrored camera with the joints, the signing space (green with a hand in
    it), and a caption. Returns False if q was pressed."""
    from ui.server import JOINT_BGR

    image = cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR)
    h, w = image.shape[:2]
    for points in (frame.pose, frame.left_hand, frame.right_hand):
        for p in points:
            cv2.circle(image, (int(p[0] * w), int(p[1] * h)), 3, JOINT_BGR, -1)
    if space is not None:
        box = SIGNING_BGR if frame.hands_in_signing_space else (150, 150, 150)
        corner = (int(space.x_min * w), int(space.y_min * h))
        cv2.rectangle(image, corner, (int(space.x_max * w), int(space.y_max * h)), box, 2)
    image = cv2.flip(image, 1)
    cv2.putText(image, text, (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 8)
    cv2.putText(image, text, (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 3)
    cv2.imshow("Record a sign", image)
    return cv2.waitKey(1) & 0xFF != ord("q")


def record(gloss: str, takes: int) -> None:
    import cv2

    from recognition.camera import Camera
    from recognition.replay import frame_to_json
    from tools.tune_recognition import signing_space

    config = load_config()
    gate = signing_space(config)  # the one saved in setup, like the app
    lib = library()
    camera = Camera(config)
    try:
        take, note = 1, ""
        while take <= takes:
            # Wait for resting hands, then count down.
            ready_since = None
            before: deque = deque(maxlen=15)  # rest before the sign, for the raw take
            while True:
                frame = camera.read()
                if frame is None:
                    continue
                frame = gate.apply(frame)
                before.append(frame)
                if frame.hands_in_signing_space:
                    ready_since = None
                    text = f"{gloss} {take}/{takes}: {note}rest your hands below the box"
                    if not show(cv2, frame, text, space=gate):
                        return
                    continue
                ready_since = ready_since or time.monotonic()
                left = 1.5 - (time.monotonic() - ready_since)
                if left <= 0:
                    break
                if not show(cv2, frame, f"{gloss} {take}/{takes}: ready... {left:.1f}", space=gate):
                    return
            # Record from hands-in to hands-out.
            clip, started, last_in, raw, too_long = [], None, None, [], False
            while True:
                frame = camera.read()
                if frame is None:
                    continue
                frame = gate.apply(frame)
                now = time.monotonic()
                (raw if started or frame.hands_in_signing_space else before).append(frame)
                if frame.hands_in_signing_space:
                    started = started or now
                    last_in = now
                    clip.append(frame)
                elif started and now - last_in > END_GAP:
                    break
                if started and now - started > MAX_SECONDS:
                    too_long = True
                    break
                label = "recording" if started else "GO: sign it inside the box"
                text = f"{gloss} {take}/{takes}: {label}"
                if not show(cv2, frame, text, (80, 220, 80), space=gate):
                    return
            if too_long or len(clip) < MIN_FRAMES:
                why = "too long: sign once, then drop your hands" if too_long else "too short"
                print(f"take {take} {why}; again")
                note = f"({why}) "
                continue
            note = ""
            try:
                path = lib.add(gloss, clip)
                frames = list(before) + raw
                with path.with_suffix(".jsonl").open("w") as f:
                    for fr in frames:
                        f.write(json.dumps(frame_to_json(fr, t=fr.ts - frames[0].ts)) + "\n")
                print(f"take {take}: {len(clip)} frames -> {path}")
                take += 1
            except ValueError as exc:
                print(f"take {take} not saved ({exc}); again")
    finally:
        camera.close()
        cv2.destroyAllWindows()


def check() -> None:
    """For each example: its nearest other example. Mistakes mean the signs are too alike."""
    lib = library()
    limit = lib.threshold()
    print(f"match threshold {limit:.3f}")
    errors = 0
    for gloss, clips in lib.examples.items():
        for i, clip in enumerate(clips):
            best = None
            for other, others in lib.examples.items():
                for j, c in enumerate(others):
                    if other == gloss and j == i:
                        continue
                    d = distance(clip, c)
                    if best is None or d < best[1]:
                        best = (other, d)
            ok = best is not None and best[0] == gloss
            errors += not ok
            nearest, d = best if best else ("-", 0.0)
            note = "" if ok else "  <- confused"
            print(f"{gloss} #{i + 1}: nearest {nearest} ({d:.3f}){note}")
    print("all examples separate" if not errors else f"{errors} confused: record more or vary less")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("gloss", nargs="?", help="the sign's gloss, e.g. WW or YOU-REMIND-ME")
    parser.add_argument("--takes", type=int, default=5)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.list:
        for gloss, clips in library().examples.items():
            print(f"{gloss}: {len(clips)} examples")
    elif args.check:
        check()
    elif args.gloss:
        record(args.gloss.upper(), args.takes)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
