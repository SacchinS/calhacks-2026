"""The engine protocol the Mac app (ui/macos, SignBridge's SwiftUI app) relies on.
No display or Swift needed."""

import asyncio
import base64
import io
import json
import sys

import pytest

from app import App
from shared.config import ROOT, load_config
from shared.events import Caption, LandmarkFrame, MockInput, OutputReply, SignEvent
from ui.server import EngineServer, render_preview


@pytest.fixture
async def engine(tmp_path):
    app = App(load_config().all_mocks())
    app.router.claude_code.chunk_delay = 0
    server = EngineServer(app, io.StringIO(), ui_config=tmp_path / "ui.json")
    await server.start()
    await app.start()
    await server.set_mode("run")
    yield server
    await app.stop()
    await server.stop()


def messages(server, kind=None):
    out = [json.loads(line) for line in server.out.getvalue().splitlines()]
    return [m for m in out if kind is None or m["type"] == kind]


async def until(condition, seconds=5.0):
    for _ in range(int(seconds / 0.02)):
        if condition():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


def last_status(server):
    return messages(server, "status")[-1]


async def test_ready_carries_the_apps_settings(engine):
    engine.send_ready()
    (ready,) = messages(engine, "ready")
    assert ready["config"]["onboarded"] is False
    assert {"still", "phrase_rest", "min_conf", "voice_device"} <= set(ready["config"])


async def test_claude_code_flow_goes_through_signbridge_states(engine):
    await engine.handle_command({"cmd": "gesture", "name": "wake"})
    assert last_status(engine)["state"] == "listening"

    await engine.handle_command({"cmd": "fake", "glosses": ["MAKE", "TITLE", "RED"]})
    await until(lambda: last_status(engine)["state"] == "confirming")
    status = last_status(engine)
    assert status["glosses"] == ["MAKE", "TITLE", "RED"]
    assert status["intent"] == {"sentence": "Make title red.", "route": "text"}
    assert status["target"] == "Claude Code"

    await engine.handle_command({"cmd": "gesture", "name": "confirm"})  # = YES
    await until(lambda: any(m["done"] for m in messages(engine, "reply")))
    await until(lambda: last_status(engine)["state"] == "idle")
    assert "sent" in last_status(engine)["log"]


async def test_cancel_while_confirming_sends_nothing(engine):
    await engine.handle_command({"cmd": "fake", "glosses": ["HELLO"]})
    await until(lambda: last_status(engine)["state"] == "confirming")
    await engine.handle_command({"cmd": "gesture", "name": "cancel"})  # = NO
    await until(lambda: last_status(engine)["state"] == "idle")
    await asyncio.sleep(0.1)
    assert messages(engine, "reply") == []
    assert "cancelled" in last_status(engine)["log"]


async def test_cancel_while_signing_clears(engine):
    engine.bus.publish(MockInput("wrong signs"))
    await until(lambda: last_status(engine)["glosses"] == ["WRONG", "SIGNS"])
    await engine.handle_command({"cmd": "gesture", "name": "cancel"})  # = CLEAR
    await until(
        lambda: last_status(engine)["state"] == "idle" and not last_status(engine)["glosses"]
    )


async def test_voice_mode_speaks_without_confirming(engine):
    await engine.handle_command({"cmd": "output_mode", "mode": "voice"})
    await until(lambda: last_status(engine)["output_mode"] == "voice")
    await engine.handle_command({"cmd": "mock_input", "text": "tomorrow rain /send"})
    await until(lambda: "sent" in last_status(engine)["log"])
    states = [m["state"] for m in messages(engine, "status")]
    assert "confirming" not in states and "sending" in states
    sending = next(m for m in messages(engine, "status") if m["state"] == "sending")
    assert sending["intent"] == {"sentence": "Tomorrow rain.", "route": "voice"}


async def test_siri_mode_types_to_siri(engine):
    typed = []
    engine.app.router.siri.send = lambda text: _record(typed, text)
    await engine.handle_command({"cmd": "output_mode", "mode": "siri"})
    await until(lambda: last_status(engine)["output_mode"] == "siri")
    assert last_status(engine)["target"] == "Siri"
    await engine.handle_command({"cmd": "mock_input", "text": "tomorrow rain /send"})
    await until(lambda: typed == ["Tomorrow rain."])
    sending = next(m for m in messages(engine, "status") if m["state"] == "sending")
    assert sending["intent"] == {"sentence": "Tomorrow rain.", "route": "siri"}


async def _record(into, text):
    into.append(text)


async def test_output_mode_picks_any_mode_and_meet_shows_captions(engine):
    await engine.handle_command({"cmd": "output_mode", "mode": "meet"})
    await until(lambda: last_status(engine)["output_mode"] == "meet")
    await until(lambda: messages(engine, "caption"))
    await engine.handle_command({"cmd": "output_mode", "mode": "claude_code"})
    await until(lambda: last_status(engine)["output_mode"] == "claude_code")


async def test_mode_off_pauses_the_recognizer(engine):
    await engine.handle_command({"cmd": "mode", "mode": "off"})
    engine.bus.publish(MockInput("hello"))
    await asyncio.sleep(0.1)
    assert last_status(engine)["glosses"] == []
    await engine.handle_command({"cmd": "mode", "mode": "run"})
    engine.bus.publish(MockInput("hello"))
    await until(lambda: last_status(engine)["glosses"] == ["HELLO"])


async def test_checks_routes_and_config(engine, tmp_path):
    await engine.handle_command({"cmd": "check", "name": "claude"})
    await until(lambda: messages(engine, "check"))
    claude = messages(engine, "check")[0]
    assert claude["ok"] is False and "mock" in claude["detail"]  # honest: the mock isn't Claude

    typed, spoken = [], []
    engine.app.router.siri.send = lambda text: _record(typed, text)
    engine.app.router.tts.send = lambda text: _record(spoken, text)
    await engine.handle_command({"cmd": "test_route", "route": "siri", "text": "What time is it?"})
    await engine.handle_command({"cmd": "test_route", "route": "voice", "text": "Voice test."})
    await until(lambda: len(messages(engine, "route_tested")) == 2)
    assert all(m["ok"] for m in messages(engine, "route_tested"))  # the mocks
    assert (typed, spoken) == (["What time is it?"], ["Voice test."])

    await engine.handle_command({"cmd": "config", "values": {"onboarded": True}})
    assert messages(engine, "config")[-1]["config"]["onboarded"] is True
    assert json.loads((tmp_path / "ui.json").read_text())["onboarded"] is True

    await engine.handle_command({"cmd": "nonsense"})
    assert messages(engine, "error")


async def test_preview_frames_and_extra_events(engine):
    pytest.importorskip("cv2")  # preview frames need the camera extra
    await engine.handle_command({"cmd": "preview", "on": True})
    hand = tuple((0.5 + i / 100, 0.4, 0.0) for i in range(21))
    engine.bus.publish(LandmarkFrame(right_hand=hand, hands_in_signing_space=True))
    await until(lambda: messages(engine, "frame"))
    jpeg = base64.b64decode(messages(engine, "frame")[0]["jpeg"])
    assert jpeg[:2] == b"\xff\xd8"
    assert render_preview(LandmarkFrame(), engine.space, mirror=True)[:2] == b"\xff\xd8"


async def test_extra_events_for_captions_and_replies(engine):
    engine.bus.publish(Caption("Hi there"))
    engine.bus.publish(OutputReply("claude_code", "Done.", done=True))
    engine.bus.publish(SignEvent("HELLO", 0.9, "isolated"))
    await until(lambda: messages(engine, "caption") and messages(engine, "reply"))
    assert messages(engine, "caption")[0]["text"] == "Hi there"
    assert messages(engine, "reply")[0] == {"type": "reply", "text": "Done.", "done": True}
    await until(lambda: "saw HELLO (90%)" in last_status(engine)["log"])


async def test_engine_process_speaks_the_protocol(tmp_path):
    """`python app.py --mock`, driven the way the Mac app drives it."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "app.py", "--mock",
        cwd=ROOT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},  # keep ui.json out of the real home
    )  # fmt: skip

    async def read_until(predicate):
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), 10)
            assert line, "engine exited early"
            message = json.loads(line)  # stdout carries nothing but protocol lines
            if predicate(message):
                return message

    def send(command):
        proc.stdin.write((json.dumps(command) + "\n").encode())

    try:
        assert (await read_until(lambda m: m["type"] == "ready"))["config"]["onboarded"] is False
        send({"cmd": "mode", "mode": "run"})
        send({"cmd": "fake", "glosses": ["ME", "WANT", "FIX", "BUG", "LOGIN", "PAGE"]})
        confirming = await read_until(
            lambda m: m["type"] == "status" and m["state"] == "confirming"
        )
        assert confirming["intent"]["sentence"] == "I want fix bug login page."
        send({"cmd": "gesture", "name": "confirm"})
        await read_until(lambda m: m["type"] == "reply" and m["done"])
        send({"cmd": "quit"})
        assert await asyncio.wait_for(proc.wait(), 10) == 0
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
