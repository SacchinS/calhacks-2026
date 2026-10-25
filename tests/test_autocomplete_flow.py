"""The scripted mock demo, through the engine protocol the Mac app uses: the other side says
"Priyanka" and "Kubernetes", the signer spells P-R-I, Priyanka is suggested, YES puts it in
the utterance, and the normal SEND -> translation -> voice flow carries on."""

import io

import pytest

from app import App
from shared.config import load_config
from shared.events import Caption
from tests.test_ui_server import last_status, messages, until
from ui.server import EngineServer


@pytest.fixture
async def engine(tmp_path):
    app = App(load_config().all_mocks())
    server = EngineServer(app, io.StringIO(), ui_config=tmp_path / "ui.json")
    await server.start()
    await app.start()
    await server.set_mode("run")
    yield server
    await app.stop()
    await server.stop()


def autocomplete(server):
    return last_status(server)["autocomplete"]


async def test_heard_in_a_meeting_then_spelled(engine):
    engine.bus.publish(
        Caption("Priyanka moved the dashboard to Kubernetes last week.", is_final=True)
    )
    await until(lambda: engine.app.vocab.for_term("PRIYANKA") != [])

    await engine.handle_command({"cmd": "mock_input", "text": "~pri"})
    await until(lambda: (autocomplete(engine) or {}).get("top") is not None)
    status = last_status(engine)
    assert status["state"] == "listening"
    assert status["autocomplete"]["letters"] == "PRI"
    assert status["autocomplete"]["top"] == {"term": "Priyanka", "kind": "name"}

    await engine.handle_command({"cmd": "mock_input", "text": "/yes"})
    await until(lambda: last_status(engine)["glosses"] == ["PRIYANKA"])
    assert last_status(engine)["autocomplete"] is None
    stats = last_status(engine)["autocomplete_stats"]
    assert stats["accepted"] == 1 and stats["letters_saved"] == 5

    await engine.handle_command({"cmd": "gesture", "name": "confirm"})  # = SEND now
    await until(lambda: messages(engine, "sent") != [])  # spoken in the call
    assert "Priyanka" in messages(engine, "sent")[0]["text"]


async def test_app_gestures_accept_an_alternate_and_dismiss(engine):
    for word in ("Kubernetes", "Kubectl"):
        engine.bus.publish(Caption(f"Ask about {word} later.", is_final=True))
    await until(lambda: len(engine.app.autocomplete.stats) >= 2)

    await engine.handle_command({"cmd": "letters", "text": "ku"})
    await until(lambda: len((autocomplete(engine) or {}).get("alternates", [])) == 1)
    alternate = autocomplete(engine)["alternates"][0]["term"]
    await engine.handle_command({"cmd": "autocomplete", "action": "accept", "index": 1})
    await until(lambda: last_status(engine)["glosses"] == [alternate.upper()])

    await engine.handle_command({"cmd": "letters", "text": "ku"})
    await until(lambda: (autocomplete(engine) or {}).get("top") is not None)
    await engine.handle_command({"cmd": "gesture", "name": "cancel"})  # NO: dismiss
    await until(lambda: autocomplete(engine)["dismissed"])
    assert autocomplete(engine)["top"] is None
    assert last_status(engine)["glosses"] == [alternate.upper()]  # the utterance is kept


async def test_settings_list_and_delete_remembered_words(engine):
    engine.bus.publish(Caption("Priyanka and Kubernetes.", is_final=True))
    await until(lambda: len(engine.app.vocab.all()) == 2)

    await engine.handle_command({"cmd": "vocab_list"})
    (listing,) = messages(engine, "vocab")
    assert {w["term"] for w in listing["words"]} == {"Priyanka", "Kubernetes"}
    word = next(w for w in listing["words"] if w["term"] == "Priyanka")
    assert word["count"] == 1 and word["occurrences"][0]["source"] == "transcript"

    await engine.handle_command({"cmd": "vocab_delete", "term": "Priyanka"})
    assert {w["term"] for w in messages(engine, "vocab")[-1]["words"]} == {"Kubernetes"}
    occ_id = messages(engine, "vocab")[-1]["words"][0]["occurrences"][0]["id"]
    await engine.handle_command({"cmd": "vocab_delete", "id": occ_id})
    assert messages(engine, "vocab")[-1]["words"] == []

    await engine.handle_command({"cmd": "letters", "text": "pri"})
    await until(lambda: (autocomplete(engine) or {}).get("letters") == "PRI")
    assert autocomplete(engine)["top"] is None  # deleted words aren't suggested
