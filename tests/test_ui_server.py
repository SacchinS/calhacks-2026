"""The engine protocol the Mac app (ui/macos) relies on. No display or Swift needed."""

import asyncio
import base64
import io
import json
import sys

import numpy as np
import pytest

from shared.bus import Bus
from shared.config import ROOT, load_config
from shared.events import (
    LandmarkFrame,
    MockInput,
    ModeChanged,
    SignEvent,
    Utterance,
)
from ui.server import EngineServer, event_to_json, frame_to_json


@pytest.fixture
def server():
    return EngineServer(Bus(), load_config().all_mocks(), io.StringIO())


def lines(server):
    return [json.loads(line) for line in server.out.getvalue().splitlines()]


def test_ready_describes_components_and_signing_space(server):
    server.send_ready({"recognizer": "mock"})
    (ready,) = lines(server)
    assert ready["type"] == "ready"
    assert ready["components"] == {"recognizer": "mock"}
    assert set(ready["signing_space"]) == {"x_min", "x_max", "y_min", "y_max"}
    assert ready["mirror"] is True


async def test_bus_events_are_forwarded_as_json(server):
    await server.start()
    server.bus.publish(ModeChanged("voice"))
    server.bus.publish(Utterance((SignEvent("TITLE", 0.9, "fingerspell"),)))
    for _ in range(20):
        await asyncio.sleep(0.01)
    await server.stop()
    mode, utterance = lines(server)
    assert (mode["type"], mode["mode"]) == ("ModeChanged", "voice")
    assert (utterance["type"], utterance["gloss"]) == ("Utterance", ["fs-TITLE"])


def test_frame_message_has_landmarks_and_optional_jpeg():
    hand = tuple((0.1 * i % 1, 0.5, 0.0) for i in range(21))
    frame = LandmarkFrame(
        right_hand=hand, pose=((0.5, 0.5, 0.0),) * 33, face=((0.5, 0.2, 0.0),) * 468
    )
    data = frame_to_json(frame)
    assert data["type"] == "LandmarkFrame"
    assert len(data["right_hand"]) == 21 and data["left_hand"] == []
    assert len(data["pose"]) == 25 and len(data["face"]) == 59
    assert all(len(p) == 2 for p in data["right_hand"])
    assert data["jpeg"] is None

    pytest.importorskip("cv2")  # JPEGs need the camera extra
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    jpeg = base64.b64decode(event_to_json(LandmarkFrame(image=image))["jpeg"])
    assert jpeg[:2] == b"\xff\xd8"


def test_commands_publish_to_the_bus(server):
    sub = server.bus.subscribe()
    assert server.handle_command({"cmd": "mock_input", "text": "hello /send"})
    assert server.handle_command({"cmd": "control", "sign": "MODE"})
    assert server.handle_command({"cmd": "control", "sign": "YES"})  # ignored: must be signed
    assert server.handle_command({"cmd": "mock_input", "text": "  "})  # ignored: empty
    assert not server.handle_command({"cmd": "quit"})
    events = [sub.get_nowait() for _ in range(sub.queue.qsize())]
    assert [type(e) for e in events] == [MockInput, SignEvent]
    assert (events[1].gloss, events[1].kind) == ("MODE", "control")


async def test_serve_stops_on_quit_or_end_of_input(server):
    reader = asyncio.StreamReader()
    reader.feed_data(b'not json\n{"cmd": "control", "sign": "CLEAR"}\n{"cmd": "quit"}\n')
    await asyncio.wait_for(server.serve(reader), 1)
    reader = asyncio.StreamReader()
    reader.feed_eof()
    await asyncio.wait_for(server.serve(reader), 1)


async def test_engine_process_speaks_the_protocol():
    """`python app.py --mock`, driven the way the Mac app drives it."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "app.py", "--mock",
        cwd=ROOT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip

    async def read_until(kind):
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), 10)
            assert line, "engine exited early"
            message = json.loads(line)  # stdout carries nothing but protocol lines
            if message["type"] == kind:
                return message

    def send(command):
        proc.stdin.write((json.dumps(command) + "\n").encode())

    try:
        ready = await read_until("ready")
        assert ready["components"]["recognizer"] == "mock"
        assert (await read_until("ModeChanged"))["mode"] == "claude_code"

        send({"cmd": "mock_input", "text": "me want fix bug login page /send"})
        request = await read_until("ConfirmRequest")
        assert request["english"] == "I want fix bug login page."
        send({"cmd": "mock_input", "text": "/yes"})
        while not (await read_until("OutputReply"))["done"]:
            pass

        send({"cmd": "control", "sign": "MODE"})
        assert (await read_until("ModeChanged"))["mode"] == "voice"
        send({"cmd": "mock_input", "text": "tomorrow rain /send"})
        sent = await read_until("OutputSent")  # mock TTS prints go to stderr, not the protocol
        assert (sent["output"], sent["text"]) == ("tts", "Tomorrow rain.")

        send({"cmd": "quit"})
        assert await asyncio.wait_for(proc.wait(), 10) == 0
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
