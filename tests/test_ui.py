from fastapi.testclient import TestClient

from shared.bus import Bus
from shared.events import ConfirmRequest, ConfirmResult, MockInput, ModeChanged, SignEvent
from ui.server import UIState, create_app, handle_message


def test_index_and_websocket_snapshot():
    state = UIState({"recognizer": "mock"})
    state.apply(ModeChanged("voice"))
    client = TestClient(create_app(Bus(), state))
    assert "<title>" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    with client.websocket_connect("/ws") as ws:
        snapshot = ws.receive_json()
    assert snapshot["type"] == "snapshot"
    assert snapshot["mode"] == "voice"


def test_state_tracks_pending_confirm():
    state = UIState({})
    state.apply(ConfirmRequest("abc", "Make the title red.", ["MAKE"]))
    assert state.snapshot()["pending"]["english"] == "Make the title red."
    state.apply(ConfirmResult("abc", True))
    assert state.snapshot()["pending"] is None


def test_browser_messages_become_bus_events():
    bus = Bus()
    sub = bus.subscribe()
    handle_message(bus, {"type": "mock_input", "text": "hello"})
    handle_message(bus, {"type": "control", "sign": "MODE"})
    handle_message(bus, {"type": "control", "sign": "YES"})  # YES must be signed, not clicked
    events = [sub.get_nowait() for _ in range(sub.queue.qsize())]
    assert events == [
        MockInput("hello", events[0].ts),
        SignEvent("MODE", 1.0, "control", events[1].ts),
    ]
