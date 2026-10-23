"""The control window: small, on the laptop screen next to the apps being driven.

Mode, status, CLEAR / MODE buttons, Claude Code's streamed reply, what was spoken,
captions in Meet mode, and the mock-sign text box (when the recognizer is the mock).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shared.events import Caption, ModeChanged, Notice, OutputReply, OutputSent
from ui import theme
from ui.bridge import BusBridge

MAX_LINES = 50


def heading(text: str) -> QLabel:
    return QLabel(text.upper(), objectName="heading")


def add_line(widget: QListWidget, text: str, color: str = theme.TEXT) -> None:
    item = QListWidgetItem(text)
    item.setForeground(QColor(color))
    widget.addItem(item)
    while widget.count() > MAX_LINES:
        widget.takeItem(0)
    widget.scrollToBottom()


class ControlWindow(QWidget):
    closing = Signal()  # closing the control window quits the app

    def __init__(self, bridge: BusBridge, components: dict[str, str]) -> None:
        super().__init__()
        self.bridge = bridge
        self.setWindowTitle("Controls")
        self.setStyleSheet(theme.STYLESHEET)
        self.resize(520, 760)

        self.mode = QLabel("…", objectName="mode")
        self.mode_button = QPushButton("MODE")
        self.clear_button = QPushButton("CLEAR")
        self.mode_button.clicked.connect(lambda: bridge.send_control("MODE"))
        self.clear_button.clicked.connect(lambda: bridge.send_control("CLEAR"))

        self.reply = QPlainTextEdit(readOnly=True)
        self.spoken = QListWidget()
        self.captions = QListWidget()
        self.captions.setFont(theme.font(theme.SIZE_M + 2))
        self.mock_input = QLineEdit(
            placeholderText="me want fix bug  ·  #title  ·  /send /yes /no /clear /mode"
        )
        self.mock_input.returnPressed.connect(self.submit_mock_input)
        sign_button = QPushButton("Sign")
        sign_button.clicked.connect(self.submit_mock_input)
        self.components = QLabel(objectName="status", wordWrap=True)
        self.set_components(components)
        self.notices = QListWidget()
        self.notices.setFont(theme.font(theme.SIZE_S))

        header = QHBoxLayout()
        header.addWidget(self.mode)
        header.addStretch()
        header.addWidget(self.mode_button)
        header.addWidget(self.clear_button)

        mock_row = QHBoxLayout()
        mock_row.addWidget(self.mock_input, stretch=1)
        mock_row.addWidget(sign_button)

        # Sections shown per mode: (widgets, modes they're visible in).
        self.sections: list[tuple[list[QWidget], set[str]]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addLayout(header)
        self._section(layout, "Claude Code", self.reply, {"claude_code"}, stretch=2)
        self._section(layout, "Spoken", self.spoken, {"voice", "meet"}, stretch=1)
        self._section(layout, "Captions", self.captions, {"meet"}, stretch=2)
        self.mock_box = QWidget()
        self.mock_box.setLayout(mock_row)
        mock_heading = heading("Mock signs")
        layout.addWidget(mock_heading)
        layout.addWidget(self.mock_box)
        mock_visible = components.get("recognizer") == "mock"
        mock_heading.setVisible(mock_visible)
        self.mock_box.setVisible(mock_visible)
        layout.addWidget(heading("Status"))
        layout.addWidget(self.components)
        layout.addWidget(self.notices, stretch=1)

        bridge.mode_changed.connect(self.on_mode)
        bridge.output_reply.connect(self.on_output_reply)
        bridge.output_sent.connect(self.on_output_sent)
        bridge.caption.connect(self.on_caption)
        bridge.notice.connect(self.on_notice)
        bridge.confirm_result.connect(
            lambda e: add_line(self.notices, "Sent to Claude Code" if e.approved else "Cancelled")
        )
        self.on_mode(ModeChanged("claude_code"))

    def _section(self, layout, title, widget, modes, stretch) -> None:
        label = heading(title)
        layout.addWidget(label)
        layout.addWidget(widget, stretch=stretch)
        self.sections.append(([label, widget], modes))

    def show_beside(self) -> None:
        """Show at the right edge of the main screen, next to the apps being driven."""
        area = QGuiApplication.primaryScreen().availableGeometry()
        width, height = min(520, area.width() // 2), min(760, area.height() - 32)
        self.setGeometry(area.right() - width - 16, area.y() + 16, width, height)
        self.show()
        self.raise_()

    def set_components(self, components: dict[str, str]) -> None:
        self.components.setText("  ·  ".join(f"{k}: {v}" for k, v in components.items()))

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.closing.emit()
        super().closeEvent(event)

    def submit_mock_input(self) -> None:
        self.bridge.send_mock_input(self.mock_input.text())
        self.mock_input.clear()

    def on_mode(self, event: ModeChanged) -> None:
        self.mode.setText(theme.MODE_LABELS.get(event.mode, event.mode))
        for widgets, modes in self.sections:
            for widget in widgets:
                widget.setVisible(event.mode in modes)

    def on_output_reply(self, event: OutputReply) -> None:
        self.reply.appendPlainText(event.text)
        if event.done:
            self.reply.appendPlainText("")

    def on_output_sent(self, event: OutputSent) -> None:
        if event.output != "claude_code":
            prefix = "" if event.output == "tts" else f"[{event.output}] "
            add_line(self.spoken, prefix + event.text)

    def on_caption(self, event: Caption) -> None:
        add_line(self.captions, event.text)

    def on_notice(self, event: Notice) -> None:
        add_line(self.notices, event.message, theme.LEVEL_COLORS.get(event.level, theme.TEXT))
