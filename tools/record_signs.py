"""Record examples of a custom sign from the webcam (recognition/custom_signs.py).

    uv sync --extra camera
    uv run python tools/record_signs.py WW --takes 5      # 5 examples of WW
    uv run python tools/record_signs.py --list            # what's recorded
    uv run python tools/record_signs.py --check           # how well the examples separate

For each take: a window shows the camera; rest your hands, wait for "GO", sign once, then
drop your hands. A take starts when your hands enter the signing space and ends when they
leave it. Examples go to models/custom_signs/<GLOSS>/ (gitignored). Record only teammates
who agree, and learn each sign from a Deaf signer or the linked source videos first.
Press q to quit early.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recognition.custom_signs import CustomSignLibrary, distance  # noqa: E402
from shared.config import load_config  # noqa: E402

MAX_SECONDS = 4.0  # longest take
END_GAP = 0.35  # hands out of the signing space this long ends the take


def library() -> CustomSignLibrary:
    return CustomSignLibrary(
        load_config().path("recognition.custom_signs_dir", "models/custom_signs")
    )


def show(cv2, frame, text: str, color=(255, 255, 255)) -> bool:
    """Draw the mirrored camera with a caption. Returns False if q was pressed."""
    image = cv2.flip(cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR), 1)
    cv2.putText(image, text, (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 8)
    cv2.putText(image, text, (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 3)
    cv2.imshow("Record a sign", image)
    return cv2.waitKey(1) & 0xFF != ord("q")


def record(gloss: str, takes: int) -> None:
    import cv2

    from recognition.camera import Camera
    from recognition.gating import SigningSpace

    config = load_config()
    gate = SigningSpace.from_config(config)
    lib = library()
    camera = Camera(config)
    try:
        for take in range(1, takes + 1):
            # Wait for resting hands, then count down.
            ready_since = None
            while True:
                frame = camera.read()
                if frame is None:
                    continue
                frame = gate.apply(frame)
                if frame.hands_in_signing_space:
                    ready_since = None
                    if not show(cv2, frame, f"{gloss} {take}/{takes}: rest your hands"):
                        return
                    continue
                ready_since = ready_since or time.monotonic()
                left = 1.5 - (time.monotonic() - ready_since)
                if left <= 0:
                    break
                if not show(cv2, frame, f"{gloss} {take}/{takes}: ready... {left:.1f}"):
                    return
            # Record from hands-in to hands-out.
            clip, started, last_in = [], None, None
            while True:
                frame = camera.read()
                if frame is None:
                    continue
                frame = gate.apply(frame)
                now = time.monotonic()
                if frame.hands_in_signing_space:
                    started = started or now
                    last_in = now
                    clip.append(frame)
                elif started and now - last_in > END_GAP:
                    break
                if started and now - started > MAX_SECONDS:
                    break
                label = "recording" if started else "GO: sign it"
                if not show(cv2, frame, f"{gloss} {take}/{takes}: {label}", (80, 220, 80)):
                    return
            try:
                path = lib.add(gloss, clip)
                print(f"take {take}: {len(clip)} frames -> {path}")
            except ValueError as exc:
                print(f"take {take} skipped: {exc}")
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
