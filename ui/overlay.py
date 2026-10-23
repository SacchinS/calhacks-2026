"""Draws a LandmarkFrame: the camera image, landmarks, the signing-space box, and labels
for recently recognized signs. Pure painting on a QPainter, so it's testable offscreen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from recognition.gating import SigningSpace
from shared.events import LandmarkFrame, Point, SignEvent
from ui import theme

# MediaPipe hand topology (21 points) and upper-body pose connections.
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]  # fmt: skip
POSE_CONNECTIONS = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24)]
DEFAULT_ASPECT = 4 / 3  # used to size the view when there's no camera image (mock, replay)
LABEL_SECONDS = 2.5  # how long a recognized sign stays on the video


@dataclass
class View:
    """Maps normalized landmark coordinates (0..1) into the video rectangle."""

    rect: QRectF
    mirror: bool

    def point(self, p: Point | tuple[float, float]) -> QPointF:
        x = 1.0 - p[0] if self.mirror else p[0]
        return QPointF(
            self.rect.left() + x * self.rect.width(), self.rect.top() + p[1] * self.rect.height()
        )


def to_qimage(image: np.ndarray) -> QImage:
    """RGB uint8 (h x w x 3) numpy array -> QImage (copied, so the array can be freed)."""
    image = np.ascontiguousarray(image, dtype=np.uint8)
    h, w = image.shape[:2]
    return QImage(image.data, w, h, image.strides[0], QImage.Format.Format_RGB888).copy()


def fit_rect(bounds: QRectF, aspect: float) -> QRectF:
    """The largest rectangle with this aspect ratio, centered in bounds."""
    w, h = bounds.width(), bounds.height()
    if w / max(h, 1) > aspect:
        w = h * aspect
    else:
        h = w / aspect
    return QRectF(bounds.center().x() - w / 2, bounds.center().y() - h / 2, w, h)


def draw_frame(
    painter: QPainter,
    bounds: QRectF,
    frame: LandmarkFrame | None,
    space: SigningSpace,
    recent_signs: Sequence[SignEvent] = (),
    now: float = 0.0,
    mirror: bool = True,
) -> QRectF:
    """Paint everything into `bounds`. Returns the rectangle the video occupies."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    image = to_qimage(frame.image) if frame is not None and frame.image is not None else None
    aspect = image.width() / image.height() if image is not None else DEFAULT_ASPECT
    view = View(fit_rect(bounds, aspect), mirror)

    if image is not None:
        if mirror:
            image = image.flipped(Qt.Orientation.Horizontal)
        painter.drawImage(view.rect, image)
    else:
        painter.fillRect(view.rect, QColor(theme.PANEL))

    if frame is not None:
        draw_signing_space(painter, view, space, frame.hands_in_signing_space)
        draw_landmarks(painter, view, frame)
    draw_sign_labels(painter, view, recent_signs, now)
    return view.rect


def draw_signing_space(painter: QPainter, view: View, space: SigningSpace, active: bool) -> None:
    color = theme.SPACE_ACTIVE if active else theme.SPACE_IDLE
    pen = QPen(color, 4 if active else 2)
    pen.setStyle(Qt.PenStyle.SolidLine if active else Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    a = view.point((space.x_min, space.y_min))
    b = view.point((space.x_max, space.y_max))
    painter.drawRect(QRectF(a, b).normalized())


def draw_landmarks(painter: QPainter, view: View, frame: LandmarkFrame) -> None:
    _draw_points(painter, view, frame.face[::4], theme.LANDMARK_FACE, radius=1.5)
    if len(frame.pose) > 24:
        _draw_lines(painter, view, frame.pose, POSE_CONNECTIONS, theme.LANDMARK_POSE, 3)
    for hand in (frame.left_hand, frame.right_hand):
        if len(hand) == 21:
            _draw_lines(painter, view, hand, HAND_CONNECTIONS, theme.LANDMARK_HAND, 3)
            _draw_points(painter, view, hand, theme.LANDMARK_HAND, radius=4)


def draw_sign_labels(painter: QPainter, view: View, signs: Sequence[SignEvent], now: float) -> None:
    """Recently recognized signs along the top of the video, newest on the right, fading."""
    visible = [s for s in signs if now - s.ts < LABEL_SECONDS][-4:]
    if not visible:
        return
    painter.setFont(theme.font(max(18, int(view.rect.height() / 14)), bold=True))
    metrics = painter.fontMetrics()
    x = view.rect.left() + 16
    y = view.rect.top() + 16
    for sign in visible:
        text = sign.gloss
        color = QColor(theme.ACCENT if sign.kind == "fingerspell" else theme.TEXT)
        if sign.kind == "control":
            color = QColor(
                theme.OK
                if sign.gloss == "YES"
                else theme.BAD
                if sign.gloss == "NO"
                else theme.MUTED
            )
        color.setAlphaF(max(0.15, 1 - (now - sign.ts) / LABEL_SECONDS))
        box = QRectF(x, y, metrics.horizontalAdvance(text) + 24, metrics.height() + 12)
        background = QColor(theme.BG)
        background.setAlphaF(0.7)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(box, 8, 8)
        painter.setPen(color)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        x += box.width() + 10


def _draw_lines(painter, view, points, connections, color, width) -> None:
    painter.setPen(QPen(color, width))
    for a, b in connections:
        if a < len(points) and b < len(points):
            painter.drawLine(view.point(points[a]), view.point(points[b]))


def _draw_points(painter, view, points, color, radius) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    for p in points:
        painter.drawEllipse(view.point(p), radius, radius)
