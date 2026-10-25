"""Record webcam landmarks to a .jsonl fixture for `recognizer: replay`.

    uv sync --extra camera
    uv run python tools/record_landmarks.py --out fixtures/my_take.jsonl --seconds 10
    uv run python tools/record_landmarks.py --out fixtures/hello.jsonl --label HELLO

Frames are written in the format recognition/replay.py reads. `--label` stamps every
frame where the hands are in the signing space (use one file per sign for training data).

For the demo script, use tools/record_script.py instead: it records phrase by phrase with
the glosses each take should give, which tools/tune_recognition.py tunes against.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recognition.camera import Camera  # noqa: E402
from recognition.gating import SigningSpace  # noqa: E402
from recognition.replay import frame_to_json  # noqa: E402
from shared.config import load_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--label", help="gloss to stamp on frames in the signing space")
    args = parser.parse_args()

    config = load_config()
    gate = SigningSpace.from_config(config)
    camera = Camera(config)
    frames = 0
    print(f"Recording {args.seconds:.0f}s to {args.out} ...")
    try:
        with args.out.open("w") as f:
            end = time.monotonic() + args.seconds
            while time.monotonic() < end:
                frame = camera.read()
                if frame is None:
                    continue
                frame = gate.apply(frame)
                if args.label and frame.hands_in_signing_space:
                    frame = replace(frame, label=args.label.upper())
                f.write(json.dumps(frame_to_json(frame)) + "\n")
                frames += 1
    finally:
        camera.close()
    print(f"Wrote {frames} frames")


if __name__ == "__main__":
    main()
