"""Large, high-contrast fonts and colors, in one place. Both windows use these.

The signer gets no audio feedback, so every state has to be readable from across a room.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

BG = "#0b0b0d"
PANEL = "#17171c"
TEXT = "#f5f5f5"
MUTED = "#8a8a94"
ACCENT = "#ffd23f"  # mode badge, fingerspelling, confirm prompt
OK = "#3ddc84"  # hands in the signing space, YES, done
WARN = "#ffb020"
BAD = "#ff5c5c"  # NO, errors

LANDMARK_HAND = QColor(OK)
LANDMARK_POSE = QColor(TEXT)
LANDMARK_FACE = QColor(MUTED)
SPACE_ACTIVE = QColor(OK)
SPACE_IDLE = QColor(MUTED)

MODE_LABELS = {"claude_code": "Claude Code", "voice": "Voice", "meet": "Meet"}
LEVEL_COLORS = {"info": TEXT, "warning": WARN, "error": BAD}

# Point sizes. The camera window is shown fullscreen on a second display, so it's huge.
SIZE_HUGE = 64  # confirm prompt
SIZE_XL = 44  # English preview on the camera window
SIZE_L = 32  # live gloss tokens, mode badge
SIZE_M = 20  # body text in the control window
SIZE_S = 14  # status / small print


def font(size: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    return f


STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: {SIZE_M}pt;
}}
QLabel {{
    background: transparent;
}}
QLabel#heading {{
    color: {MUTED};
    font-size: {SIZE_S}pt;
    font-weight: bold;
    letter-spacing: 1px;
}}
QLabel#mode {{
    background: {ACCENT};
    color: #000;
    font-size: {SIZE_L}pt;
    font-weight: 800;
    padding: 4px 16px;
    border-radius: 8px;
}}
QLabel#token {{
    font-size: {SIZE_L}pt;
    font-weight: bold;
    padding: 2px 10px;
    border: 2px solid {TEXT};
    border-radius: 6px;
}}
QLabel#token[fingerspell="true"] {{
    color: {ACCENT};
    border: 2px dashed {ACCENT};
}}
QLabel#english {{
    font-size: {SIZE_XL}pt;
    font-weight: bold;
}}
QFrame#confirm {{
    background: {PANEL};
    border: 6px solid {ACCENT};
    border-radius: 16px;
}}
QLabel#confirmTitle {{
    color: {ACCENT};
    font-size: {SIZE_L}pt;
    font-weight: bold;
}}
QLabel#confirmText {{
    font-size: {SIZE_HUGE}pt;
    font-weight: bold;
}}
QLabel#confirmHint {{
    font-size: {SIZE_L}pt;
}}
QLabel#status {{
    color: {MUTED};
    font-size: {SIZE_S}pt;
}}
QPushButton {{
    font-weight: bold;
    padding: 8px 18px;
    border: 2px solid {TEXT};
    border-radius: 8px;
}}
QPushButton:pressed {{
    background: {TEXT};
    color: {BG};
}}
QPlainTextEdit, QListWidget, QLineEdit {{
    background: {PANEL};
    border: 2px solid {PANEL};
    border-radius: 8px;
    padding: 6px;
}}
QLineEdit:focus {{
    border: 2px solid {ACCENT};
}}
"""
