"""Record the demo script from the webcam, phrase by phrase, for tuning recognition.

    uv sync --extra camera
    uv run python tools/record_script.py                  # every phrase, 3 takes each
    uv run python tools/record_script.py --takes 5 --only 1 3      # phrases 1 and 3
    uv run python tools/record_script.py --phrase "HELLO, NICE MEET YOU" --takes 3
    uv run python tools/record_script.py --list
    uv run python tools/tune_recognition.py               # then: tune on what you recorded

For each take: a window shows the camera and the phrase; rest your hands, wait for "GO",
sign the whole phrase at your normal speed, then drop your hands. The take ends when your
hands have been down for `--rest` seconds (like "Rest to finish" in the app).

Takes go to models/takes/ (gitignored: it's a teammate's body-tracking data), one .jsonl
per take in the replay format, plus manifest.json with the glosses each take should give.
Any take can be replayed with `recognizer: replay`, `recognition.replay_file: <the take>`
and `recognition.replay_classifier: model`. Record only teammates who agree, and learn the
signs from a Deaf signer or the source videos in docs/asl-demo-script-research.md first.
Press q to quit early (the takes so far are kept).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recognition.replay import frame_to_json  # noqa: E402
from shared.config import ROOT, load_config  # noqa: E402

TAKES_DIR = ROOT / "models" / "takes"
MAX_SECONDS = 15.0  # longest take

# The Meet demo (MVP.md, docs/asl-demo-script-research.md Moment 3) and the control signs, in
# the mock-sign syntax. `~pri` is fingerspelled letter by letter, then YES takes the
# autocomplete's suggestion; the tuner scores only the signs. Drafts until a Deaf signer
# approves them.
SCRIPT = [
    "HELLO, NICE MEET YOU",
    "~pri YES",
    "HOW YOU [wh]",
    "FINE, THANK-YOU",
    "~fi YES",
    "YES",
    "NO",
    "FINISH",
]


def slug(phrase: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", phrase.lower()).strip("-")[:40] or "take"


def load_manifest(folder: Path = TAKES_DIR) -> dict[str, str]:
    """{take file name: the phrase it should be recognized as}."""
    path = folder / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_take(phrase: str, frames: list, folder: Path = TAKES_DIR) -> Path:
    """Write one take (frames with seconds since its start) and add it to the manifest."""
    folder.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(folder)
    n = 1 + sum(1 for p in manifest.values() if p == phrase)
    path = folder / f"{slug(phrase)}-{n:02d}.jsonl"
    while path.name in manifest or path.exists():
        n += 1
        path = folder / f"{slug(phrase)}-{n:02d}.jsonl"
    start = frames[0].ts if frames else 0.0
    with path.open("w") as f:
        for frame in frames:
            f.write(json.dumps(frame_to_json(frame, t=frame.ts - start)) + "\n")
    manifest[path.name] = phrase
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def record(phrases: list[str], takes: int, rest: float) -> None:
    import cv2

    from recognition.camera import Camera
    from tools.record_signs import show
    from tools.tune_recognition import signing_space

    config = load_config()
    gate = signing_space(config)  # the one saved in setup, like the app
    camera = Camera(config)
    try:
        for i, phrase in enumerate(phrases, 1):
            for take in range(1, takes + 1):
                title = f"{i}/{len(phrases)} {phrase} ({take}/{takes})"
                # Wait for resting hands, then count down.
                ready_since = None
                while True:
                    frame = camera.read()
                    if frame is None:
                        continue
                    frame = gate.apply(frame)
                    if frame.hands_in_signing_space:
                        ready_since = None
                        if not show(cv2, frame, f"{title}: rest your hands", space=gate):
                            return
                        continue
                    ready_since = ready_since or time.monotonic()
                    left = 1.5 - (time.monotonic() - ready_since)
                    if left <= 0:
                        break
                    if not show(cv2, frame, f"{title}: ready... {left:.1f}", space=gate):
                        return
                # Record everything from the first sign until the hands rest.
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
                    if started:
                        clip.append(frame)
                        if now - last_in > rest or now - started > MAX_SECONDS:
                            break
                    label = "recording" if started else "GO: sign it"
                    if not show(cv2, frame, f"{title}: {label}", (80, 220, 80), space=gate):
                        return
                if len(clip) < 10:
                    print(f"{phrase} take {take}: too short, skipped")
                    continue
                path = save_take(phrase, clip)
                print(f"{phrase} take {take}: {len(clip)} frames -> {path.relative_to(ROOT)}")
    finally:
        camera.close()
        cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--takes", type=int, default=3)
    parser.add_argument("--only", type=int, nargs="*", help="phrase numbers from --list")
    parser.add_argument("--phrase", action="append", help="record this phrase instead")
    parser.add_argument("--rest", type=float, default=1.5, help="hands down this long ends it")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        for i, phrase in enumerate(SCRIPT, 1):
            print(f"{i}. {phrase}")
        counts: dict[str, int] = {}
        for phrase in load_manifest().values():
            counts[phrase] = counts.get(phrase, 0) + 1
        if counts:
            print("\nRecorded:")
            for phrase, n in counts.items():
                print(f"  {phrase}: {n} takes")
        return
    phrases = args.phrase or ([SCRIPT[i - 1] for i in args.only] if args.only else SCRIPT)
    record(phrases, args.takes, args.rest)


if __name__ == "__main__":
    main()
