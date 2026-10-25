"""Try fingerspelled letters live: the camera, the letter the model sees, and the letters the
app would count, so you can check the model and settle `recognition.letter_orientation`.

    uv sync --extra camera
    uv run python tools/try_letters.py                # q quits
    uv run python tools/try_letters.py --orientation mirrored

Keep one hand inside the green box (the signing space you saved in setup). Hold each
letter for `letter_hold_seconds` (5 s in the slow testing settings), then change to the
next; for the same letter twice, drop your hand in between.

- Line 1: the model's guess this frame, as the camera sees the hand and mirrored. Only the
  letters in `recognition.letter_set` are read (PRIKUB for the demo; empty = A-Z).
- Line 2: why it is or isn't counted: unsure (under `letter_threshold`), holding (not yet
  `letter_hold_seconds`), counted, or waiting for a second letter (a word's first letter
  shows only once the second is held, so a sign's handshape isn't read as a letter).
- Line 3: the counted letters, the way autocomplete gets them. Fingerspelling has no space
  sign: a word ends when you pause (`letter_end_seconds`) or sign something else, shown
  here as a space.

On quitting it prints which orientation read your hand more surely: put that in
config.yaml. Nothing is saved.
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

    import json

    import cv2

    from recognition.camera import Camera
    from recognition.fingerspelling import ORIENTATIONS, LetterModel, LetterReader
    from recognition.gating import SigningSpace
    from ui.server import UI_CONFIG

    config = load_config()
    if args.orientation:
        config.sections.setdefault("recognition", {})["letter_orientation"] = args.orientation
    space = SigningSpace.from_config(config)
    try:  # the position saved in the app's setup ("Save This Position")
        space = SigningSpace(**json.loads(UI_CONFIG.read_text())["signing_space"])
    except (OSError, KeyError, TypeError, ValueError):
        pass
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
            was_spelling = reader.spelling
            spelled += "".join(letter.letter for letter in reader.push(frame, space))
            if was_spelling and not reader.spelling and not spelled.endswith(" "):
                spelled += " "  # the word ended
            if not draw(cv2, frame, space, [line, reader.status, spelled[-24:] or "-"]):
                break
    finally:
        camera.close()
        cv2.destroyAllWindows()
    if wins:
        best, _ = wins.most_common(1)[0]
        print(f"Surer reads: {dict(wins)}. Set recognition.letter_orientation: {best}")
    print(f"Counted: {spelled or '(nothing)'}")


def draw(cv2, frame, space, lines: list[str]) -> bool:
    """The mirrored camera, the signing space, and three lines. False if q was pressed."""
    image = cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR)
    h, w = image.shape[:2]
    corner = (int(space.x_min * w), int(space.y_min * h))
    cv2.rectangle(image, corner, (int(space.x_max * w), int(space.y_max * h)), (80, 220, 80), 2)
    image = cv2.flip(image, 1)
    for i, text in enumerate(lines):
        y, size = 50 + 50 * i, 1.4 if i == 2 else 0.9
        cv2.putText(image, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX, size, (0, 0, 0), 6)
        cv2.putText(image, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX, size, (255, 255, 255), 2)
    cv2.imshow("Try letters", image)
    return cv2.waitKey(1) & 0xFF != ord("q")


if __name__ == "__main__":
    main()
