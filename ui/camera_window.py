"""The camera window: what the signer (and the judges) watch.

Webcam feed with the landmark overlay and signing-space box, each recognized sign as it
lands, the live gloss, the English preview, and a big YES/NO confirm prompt. Everything
the signer needs fits in this window alone.

Fullscreen on any display: press F (or double-click), or right-click > Move to display.
Esc leaves fullscreen. The window remembers its display and fullscreen state.
"""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QPainter, QScreen, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

from recognition.gating import SigningSpace
from shared.config import Config
from shared.events import (
    Caption,
    ConfirmRequest,
    ConfirmResult,
    LandmarkFrame,
    ModeChanged,
    Notice,
    OutputReply,
    OutputSent,
    SignEvent,
    Translation,
    UtteranceProgress,
)
from ui import overlay, theme
from ui.bridge import BusBridge

MAX_TOKENS = 10  # gloss tokens shown at once (newest)
CONTROL_WIDTH = 520  # the control window's default width, kept clear on first run


def make_settings() -> QSettings:
    return QSettings("calhacks-2026", "calhacks-2026")


class VideoView(QWidget):
    """Paints the latest LandmarkFrame with the overlay."""

    def __init__(self, space: SigningSpace, mirror: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.space = space
        self.mirror = mirror
        self.frame: LandmarkFrame | None = None
        self.recent_signs: deque[SignEvent] = deque(maxlen=8)
        self.placeholder = (
            "No camera feed with the mock recognizer.\nType signs in the control window."
        )
        self.setMinimumSize(320, 240)
        # Repaint while sign labels fade out, even if no new frames arrive (mock mode).
        self._fade = QTimer(self, interval=100, timeout=self.update)

    def set_frame(self, frame: LandmarkFrame) -> None:
        self.frame = frame
        self.update()

    def add_sign(self, sign: SignEvent) -> None:
        self.recent_signs.append(sign)
        self._fade.start()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        now = time.time()
        rect = overlay.draw_frame(
            painter,
            QRectF(self.rect()),
            self.frame,
            self.space,
            self.recent_signs,
            now,
            self.mirror,
        )
        if self.frame is None:
            painter.setPen(Qt.GlobalColor.gray)
            painter.setFont(theme.font(theme.SIZE_M))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.placeholder)
        if not any(now - s.ts < overlay.LABEL_SECONDS for s in self.recent_signs):
            self._fade.stop()
        painter.end()


class CameraWindow(QWidget):
    def __init__(
        self, bridge: BusBridge, config: Config, settings: QSettings | None = None
    ) -> None:
        super().__init__()
        self.bridge = bridge
        self.settings = settings or make_settings()
        self.setWindowTitle("Camera")
        self.setStyleSheet(theme.STYLESHEET)
        self.resize(1100, 850)

        self.mode = QLabel("…", objectName="mode")
        self.video = VideoView(
            SigningSpace.from_config(config), bool(config.get("ui.mirror_camera", True))
        )
        self.gloss_row = QHBoxLayout()
        self.gloss_row.setSpacing(8)
        self.english = QLabel("", objectName="english", wordWrap=True)
        self.caption = QLabel("", wordWrap=True)
        self.caption.setFont(theme.font(theme.SIZE_L))
        self.caption.hide()
        self.status = QLabel("", objectName="status", wordWrap=True)

        self.confirm = QFrame(objectName="confirm")
        self.confirm_text = QLabel("", objectName="confirmText", wordWrap=True)
        confirm_layout = QVBoxLayout(self.confirm)
        confirm_layout.addWidget(QLabel("Send to Claude Code?", objectName="confirmTitle"))
        confirm_layout.addWidget(self.confirm_text)
        confirm_layout.addWidget(
            QLabel(
                f'Sign <b style="color:{theme.OK}">YES</b> to send &nbsp;·&nbsp; '
                f'Sign <b style="color:{theme.BAD}">NO</b> to cancel',
                objectName="confirmHint",
            )
        )
        self.confirm.hide()
        self.pending_id: str | None = None

        header = QHBoxLayout()
        header.addWidget(self.mode)
        header.addStretch()
        hint = QLabel("F: fullscreen · right-click: move to display", objectName="status")
        header.addWidget(hint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addLayout(header)
        layout.addWidget(self.video, stretch=1)
        layout.addLayout(self.gloss_row)
        layout.addWidget(self.english)
        layout.addWidget(self.confirm)
        layout.addWidget(self.caption)
        layout.addWidget(self.status)

        QShortcut(QKeySequence("F"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence.StandardKey.FullScreen, self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self.leave_fullscreen)

        bridge.mode_changed.connect(self.on_mode)
        bridge.frame.connect(self.video.set_frame)
        bridge.sign.connect(self.video.add_sign)
        bridge.progress.connect(self.on_progress)
        bridge.translation.connect(self.on_translation)
        bridge.confirm_request.connect(self.on_confirm_request)
        bridge.confirm_result.connect(self.on_confirm_result)
        bridge.caption.connect(self.on_caption)
        bridge.output_sent.connect(self.on_output_sent)
        bridge.output_reply.connect(self.on_output_reply)
        bridge.notice.connect(self.on_notice)

    # Bus events

    def on_mode(self, event: ModeChanged) -> None:
        self.mode.setText(theme.MODE_LABELS.get(event.mode, event.mode))
        self.caption.setVisible(event.mode == "meet" and bool(self.caption.text()))
        self._mode = event.mode

    def on_progress(self, event: UtteranceProgress) -> None:
        while self.gloss_row.count():
            item = self.gloss_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for token in event.gloss[-MAX_TOKENS:]:
            fingerspelled = token.startswith("fs-")
            label = QLabel(token.removeprefix("fs-"), objectName="token")
            label.setProperty("fingerspell", "true" if fingerspelled else "false")
            self.gloss_row.addWidget(label)
        self.gloss_row.addStretch()

    def on_translation(self, event: Translation) -> None:
        self.english.setText(event.english)

    def on_confirm_request(self, event: ConfirmRequest) -> None:
        self.pending_id = event.request_id
        self.confirm_text.setText(event.english)
        self.confirm.show()

    def on_confirm_result(self, event: ConfirmResult) -> None:
        if event.request_id != self.pending_id:
            return
        self.pending_id = None
        self.confirm.hide()
        self.set_status("Sent to Claude Code" if event.approved else "Cancelled", "info")

    def on_caption(self, event: Caption) -> None:
        self.caption.setText(f"Them: {event.text}")
        self.caption.setVisible(getattr(self, "_mode", None) == "meet")

    def on_output_sent(self, event: OutputSent) -> None:
        if event.output != "claude_code":
            self.set_status(f"Spoken: {event.text}", "info")

    def on_output_reply(self, event: OutputReply) -> None:
        self.set_status(f"Claude Code: {event.text}", "info")

    def on_notice(self, event: Notice) -> None:
        if event.level != "info":
            self.set_status(event.message, event.level)

    def set_status(self, text: str, level: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {theme.LEVEL_COLORS.get(level, theme.TEXT)}")

    # Display placement

    def toggle_fullscreen(self) -> None:
        self.place_on(self.screen(), fullscreen=not self.isFullScreen())

    def leave_fullscreen(self) -> None:
        if self.isFullScreen():
            self.place_on(self.screen(), fullscreen=False)

    def place_on(self, screen: QScreen, fullscreen: bool) -> None:
        """Move the window to `screen`, fullscreen or windowed, and remember it."""
        if self.isFullScreen():
            self.showNormal()
        if self.screen() is not screen:
            area = screen.availableGeometry()
            size = self.size().boundedTo(area.size())
            self.setGeometry(
                area.x() + (area.width() - size.width()) // 2,
                area.y() + (area.height() - size.height()) // 2,
                size.width(),
                size.height(),
            )
        if fullscreen:
            self.showFullScreen()
        else:
            self.show()
        self.save_placement(screen)

    def save_placement(self, screen: QScreen | None = None) -> None:
        self.settings.setValue("camera/screen", (screen or self.screen()).name())
        self.settings.setValue("camera/fullscreen", self.isFullScreen())
        if not self.isFullScreen():
            self.settings.setValue("camera/geometry", self.saveGeometry())
        self.settings.sync()

    def saved_screen(self) -> QScreen:
        """The display the window was last on, or the primary display if it's gone."""
        name = self.settings.value("camera/screen", "", type=str)
        for screen in QGuiApplication.screens():
            if screen.name() == name:
                return screen
        return QGuiApplication.primaryScreen()

    def show_restored(self) -> None:
        """Show on the remembered display, fullscreen if it was fullscreen."""
        geometry = self.settings.value("camera/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:  # first run: the left of the main screen, leaving room for the control window
            area = QGuiApplication.primaryScreen().availableGeometry()
            width = max(480, area.width() - CONTROL_WIDTH - 48)
            self.setGeometry(area.x() + 16, area.y() + 16, width, area.height() - 32)
        fullscreen = self.settings.value("camera/fullscreen", False, type=bool)
        self.place_on(self.saved_screen(), fullscreen)

    def moveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().moveEvent(event)
        if self.isVisible():
            self.save_placement()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.save_placement()
        super().closeEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt override)
        menu = QMenu(self)
        fullscreen = QAction("Fullscreen", menu, checkable=True, checked=self.isFullScreen())
        fullscreen.triggered.connect(self.toggle_fullscreen)
        menu.addAction(fullscreen)
        displays = menu.addMenu("Move to display (fullscreen)")
        for screen in QGuiApplication.screens():
            action = displays.addAction(screen.name())
            action.triggered.connect(lambda _=False, s=screen: self.place_on(s, fullscreen=True))
        menu.exec(event.globalPos())

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.toggle_fullscreen()
