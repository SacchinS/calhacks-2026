"""UI tests. They run without a display (QT_QPA_PLATFORM=offscreen, set in conftest.py)."""

import asyncio

import numpy as np
import pytest
from PySide6.QtCore import QRectF, QSettings
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app import App
from recognition.gating import SigningSpace
from recognition.replay import read_fixture
from shared.bus import Bus
from shared.config import ROOT, load_config
from shared.events import (
    Caption,
    ConfirmRequest,
    ConfirmResult,
    LandmarkFrame,
    MockInput,
    ModeChanged,
    SignEvent,
    UtteranceProgress,
)
from ui import overlay, theme
from ui.bridge import BusBridge
from ui.camera_window import CameraWindow
from ui.control_window import ControlWindow


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def config():
    return load_config().all_mocks()


async def until(condition, seconds=5.0):
    for _ in range(int(seconds / 0.02)):
        if condition():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


async def test_bridge_reemits_bus_events_as_signals(qapp):
    bus = Bus()
    bridge = BusBridge(bus)
    got = []
    bridge.caption.connect(got.append)
    bridge.mode_changed.connect(got.append)
    bridge.frame.connect(got.append)
    await bridge.start()
    bus.publish(Caption("hi"))
    bus.publish(ModeChanged("meet"))
    bus.publish(LandmarkFrame())
    await until(lambda: len(got) == 3)
    await bridge.stop()
    assert {type(e) for e in got} == {Caption, ModeChanged, LandmarkFrame}


async def test_bridge_buttons_publish_clear_and_mode_only(qapp):
    bus = Bus()
    sub = bus.subscribe()
    bridge = BusBridge(bus)
    bridge.send_control("MODE")
    bridge.send_mock_input("hello")
    bridge.send_mock_input("   ")  # ignored
    with pytest.raises(ValueError):
        bridge.send_control("YES")  # YES / NO must be signed
    events = [sub.get_nowait() for _ in range(sub.queue.qsize())]
    assert [type(e) for e in events] == [SignEvent, MockInput]
    assert (events[0].gloss, events[0].kind) == ("MODE", "control")


def test_control_window_sections_follow_mode(qapp):
    window = ControlWindow(BusBridge(Bus()), {"recognizer": "mock"})
    window.bridge.mode_changed.emit(ModeChanged("claude_code"))
    assert not window.reply.isHidden() and window.captions.isHidden()
    window.bridge.mode_changed.emit(ModeChanged("meet"))
    assert window.mode.text() == "Meet"
    assert window.reply.isHidden() and not window.captions.isHidden()
    assert not window.spoken.isHidden()
    assert not window.mock_box.isHidden()
    assert ControlWindow(BusBridge(Bus()), {"recognizer": "camera"}).mock_box.isHidden()


def test_camera_window_shows_gloss_and_confirm_prompt(qapp, config, settings):
    bridge = BusBridge(Bus())
    window = CameraWindow(bridge, config, settings)
    bridge.progress.emit(UtteranceProgress(("MAKE", "fs-TITLE", "RED")))
    tokens = [window.gloss_row.itemAt(i).widget() for i in range(window.gloss_row.count())]
    labels = [(t.text(), t.property("fingerspell")) for t in tokens if t is not None]
    assert labels == [("MAKE", "false"), ("TITLE", "true"), ("RED", "false")]

    bridge.confirm_request.emit(ConfirmRequest("r1", "Make the title red.", ["MAKE"]))
    assert not window.confirm.isHidden()
    assert window.confirm_text.text() == "Make the title red."
    bridge.confirm_result.emit(ConfirmResult("other", True))  # not ours: stays up
    assert not window.confirm.isHidden()
    bridge.confirm_result.emit(ConfirmResult("r1", False))
    assert window.confirm.isHidden()
    assert window.status.text() == "Cancelled"


def test_camera_window_remembers_display(qapp, config, settings):
    screen = QGuiApplication.primaryScreen()
    window = CameraWindow(BusBridge(Bus()), config, settings)
    window.place_on(screen, fullscreen=False)
    assert settings.value("camera/screen") == screen.name()
    window.close()

    reopened = CameraWindow(BusBridge(Bus()), config, settings)
    assert reopened.saved_screen() is screen
    settings.setValue("camera/screen", "a display that was unplugged")
    assert reopened.saved_screen() is QGuiApplication.primaryScreen()


def paint(frame, signs=(), now=0.0, size=(640, 480)):
    image = QImage(*size, QImage.Format.Format_RGB32)
    image.fill(QColor("black"))
    painter = QPainter(image)
    overlay.draw_frame(painter, QRectF(image.rect()), frame, SigningSpace(), signs, now)
    painter.end()
    return image


def count_color(image, color):
    target = QColor(color).rgb()
    return sum(
        image.pixel(x, y) == target
        for x in range(0, image.width(), 2)
        for y in range(0, image.height(), 2)
    )


def test_overlay_draws_landmarks_box_and_labels(qapp):
    frames = [
        SigningSpace().apply(f) for f in read_fixture(ROOT / "fixtures/landmarks_sample.jsonl")
    ]
    signing = next(f for f in frames if f.hands_in_signing_space)
    empty = paint(None)
    drawn = paint(signing)
    assert count_color(drawn, theme.OK) > 50  # green hands + active signing-space box
    assert count_color(empty, theme.OK) == 0

    sign = SignEvent("HELLO", 0.9, "isolated", ts=100.0)
    assert paint(None, [sign], now=100.5) != empty  # fresh label is drawn
    assert paint(None, [sign], now=110.0) == empty  # old label has faded away


def test_overlay_draws_camera_image_mirrored(qapp):
    rgb = np.zeros((60, 80, 3), dtype=np.uint8)
    rgb[:, :40] = (255, 0, 0)  # left half red in the camera image
    image = paint(LandmarkFrame(image=rgb), size=(80, 60))
    assert QColor(image.pixel(70, 30)).red() > 200  # mirrored: red is on the right
    assert QColor(image.pixel(10, 30)).red() < 50

    view = overlay.View(QRectF(0, 0, 100, 100), mirror=True)
    assert view.point((0.25, 0.5)).x() == 75


async def test_windows_update_live_from_mock_signs(qapp, config, settings):
    app = App(config)
    app.router.claude_code.chunk_delay = 0
    app.captions.interval = 0.05
    bridge = BusBridge(app.bus)
    camera = CameraWindow(bridge, config, settings)
    control = ControlWindow(bridge, app.chosen)
    await bridge.start()
    await app.start()

    def type_sign(text):
        control.mock_input.setText(text)
        control.submit_mock_input()

    try:
        type_sign("me want fix bug login page")
        type_sign("/send")
        await until(lambda: not camera.confirm.isHidden())
        assert camera.confirm_text.text() == "I want fix bug login page."
        assert camera.english.text() == "I want fix bug login page."

        type_sign("/yes")
        await until(lambda: "Done." in control.reply.toPlainText())
        assert camera.confirm.isHidden()

        control.mode_button.click()
        await until(lambda: camera.mode.text() == "Voice")
        type_sign("tomorrow rain /send")
        await until(lambda: control.spoken.count() == 1)
        assert control.spoken.item(0).text() == "Tomorrow rain."
        assert camera.status.text() == "Spoken: Tomorrow rain."

        control.mode_button.click()
        await until(lambda: control.captions.count() >= 2)
        assert camera.caption.text().startswith("Them: ")
    finally:
        await app.stop()
        await bridge.stop()


async def test_replay_frames_reach_the_camera_view(qapp, config, settings):
    config.recognizer = "replay"
    config.sections["recognition"]["replay_fps"] = 500
    app = App(config)
    bridge = BusBridge(app.bus)
    camera = CameraWindow(bridge, config, settings)
    await bridge.start()
    await app.start()
    try:
        await until(lambda: camera.video.frame is not None and camera.video.recent_signs)
        camera.video.grab()  # paints the replayed landmarks without errors
    finally:
        await app.stop()
        await bridge.stop()
