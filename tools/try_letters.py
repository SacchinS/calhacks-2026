"""Try fingerspelled letters live: the camera, the letter the model sees, and the letters the
app would count, so you can check the model and settle `recognition.letter_orientation`.

    uv sync --extra camera
    uv run python tools/try_letters.py                # q quits
    uv run python tools/try_letters.py --orientation mirrored

Hold each letter still for a moment, then move to the next; slide a little for a double
letter. The top line is the model's guess for this frame, as the camera sees the hand and
mirrored. Counted letters show below, the way autocomplete gets them (the first letter of a
word appears once the second is held). On quitting it prints which orientation read your
hand more surely: put that in config.yaml. Nothing is saved.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import load_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--orientation", choices=["auto", "as_is", "mirrored"])
    args = parser.parse_args()

    import cv2

    from recognition.camera import Camera
    from recognition.fingerspelling import ORIENTATIONS, LetterModel, LetterReader
    from recognition.gating import SigningSpace
    from tools.record_signs import show

    config = load_config()
    if args.orientation:
        config.sections.setdefault("recognition", {})["letter_orientation"] = args.orientation
    space = SigningSpace.from_config(config)
    model = LetterModel(config)
    each = {o: LetterModel(config, model.run, model.classes) for o in ORIENTATIONS}
    for orientation, m in each.items():
        m.orientation = orientation
    reader = LetterReader(config, model)
    wins: Counter[str] = Counter()
    spelled = ""
    camera = Camera(config)
    try:
        while True:
            frame = camera.read()
            if frame is None:
                continue
            hand = reader.spelling_hand(frame, space)
            line = "raise one hand into the box"
            if hand:
                guesses = {o: m.predict(hand) for o, m in each.items()}
                line = "   ".join(f"{o}: {g[0]} {g[1]:.0%}" for o, g in guesses.items() if g)
                surest = max(guesses, key=lambda o: guesses[o][1] if guesses[o] else 0)
                if guesses[surest] and guesses[surest][1] >= reader.threshold:
                    wins[surest] += 1
            spelled += "".join(letter.letter for letter in reader.push(frame, space))
            if not show(cv2, frame, f"{line}  |  {spelled[-14:] or '-'}", (80, 220, 80)):
                break
    finally:
        camera.close()
        cv2.destroyAllWindows()
    if wins:
        best, _ = wins.most_common(1)[0]
        print(f"Surer reads: {dict(wins)}. Set recognition.letter_orientation: {best}")
    print(f"Counted: {spelled or '(nothing)'}")


if __name__ == "__main__":
    main()
