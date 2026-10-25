from types import SimpleNamespace

import pytest

from language.tickets import CallNotes, TicketAgent, TicketDraft, TicketDrafter
from outputs.jira import JiraClient, JiraError
from shared.bus import Bus
from shared.config import Config
from shared.events import Caption, OutputSent, SignEvent


def ticket_config(**sections):
    base = {
        "tickets": {
            "enabled": True,
            "settle_seconds": 0,
            "notes_max": 10,
            "model": "claude-haiku-5-5",
        },
        "meet": {"signer_name": "Sacchin"},
    }
    base.update(sections)
    return Config(sections=base)


def response(payload, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=payload)],
    )


class FakeMessages:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class FakeClient:
    def __init__(self, result):
        self.messages = FakeMessages(result)
        self.beta = SimpleNamespace(messages=self.messages)


@pytest.mark.asyncio
async def test_drafter_uses_haiku_shape_without_fallbacks():
    client = FakeClient(response('{"ticket": null}'))
    drafter = TicketDrafter(ticket_config(), client=client)
    assert (
        await drafter.draft("them: update the dashboard", None, [], [], "2026-10-25", "Sacchin")
        is None
    )
    call = client.messages.calls[0]
    assert "betas" not in call and "fallbacks" not in call
    assert call["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_drafter_parses_valid_ticket_and_refusal_is_safe():
    payload = {
        "ticket": {
            "summary": "Fix the dashboard release",
            "description": "Update the dashboard and verify the release.",
            "asked": "Sacchin",
            "due": "2026-10-26",
            "labels": ["release"],
            "people": ["Pranav"],
            "assign_to_signer": True,
            "ready": True,
            "reasons": ["The meeting assigned the work."],
        }
    }
    client = FakeClient(response(__import__("json").dumps(payload)))
    drafter = TicketDrafter(ticket_config(), client=client)
    draft = await drafter.draft(
        "them: Sacchin, can you do this?", None, [], [], "2026-10-25", "Sacchin"
    )
    assert draft == TicketDraft(
        "Fix the dashboard release",
        "Update the dashboard and verify the release.",
        "Sacchin",
        "2026-10-26",
        ("release",),
        ("Pranav",),
        True,
        True,
        ("The meeting assigned the work.",),
    )

    refusal = FakeClient(response("", stop_reason="refusal"))
    assert await TicketDrafter(ticket_config(), client=refusal).draft("notes", None, [], []) is None


@pytest.mark.asyncio
async def test_ready_yes_creates_once_and_early_yes_does_nothing():
    bus = Bus()
    config = ticket_config()

    class Drafter:
        model = "claude-haiku-5-5"

        def __init__(self):
            self.calls = 0

        async def draft(self, *args, **kwargs):
            self.calls += 1
            ready = self.calls > 1
            return TicketDraft(
                "Fix the dashboard",
                "Update the dashboard release.",
                asked="Sacchin" if ready else "",
                due="2026-10-26" if ready else "",
                labels=("release",),
                assign_to_signer=ready,
                ready=ready,
                reasons=("The meeting discussed the work.",),
            )

    class Announcer:
        def __init__(self):
            self.texts = []

        async def announce(self, text):
            self.texts.append(text)

    announcer = Announcer()
    agent = TicketAgent(bus, config, JiraClient(config), drafter=Drafter(), announcer=announcer)
    agent.notes.on_event(Caption("Sacchin, please fix the dashboard.", is_final=True))
    first = await agent.draft_now()
    assert first.ready is False
    assert await agent.handle_control(SignEvent("YES", 1, "control")) is True
    assert agent.update.state == "tentative"
    second = await agent.draft_now()
    assert second.ready is True
    assert await agent.handle_control(SignEvent("YES", 1, "control")) is True
    assert agent.update.state == "created"
    assert agent.update.key == "MOCK-1"
    assert announcer.texts == ["I've added it to Jira as MOCK-1."]
    assert await agent.handle_control(SignEvent("YES", 1, "control")) is False


@pytest.mark.asyncio
async def test_failed_create_retries_the_same_version_once():
    bus = Bus()
    config = ticket_config()

    class Drafter:
        model = "claude-haiku-5-5"

        async def draft(self, *args, **kwargs):
            return TicketDraft("Fix the dashboard", "Update the dashboard release.", ready=True)

    class FlakyJira:
        mock = False

        def __init__(self):
            self.request_ids = []

        async def context(self, summary, terms):
            return {"similar": [], "release": []}

        async def create(self, ticket, audit):
            self.request_ids.append(f"{audit['call_id']}-v{audit['draft_version']}")
            if len(self.request_ids) == 1:
                raise JiraError("timed out")
            return {"key": "SB-9", "url": "", "audit_saved": True}

    jira = FlakyJira()
    agent = TicketAgent(bus, config, jira, drafter=Drafter())
    agent.notes.on_event(Caption("Sacchin, please fix the dashboard.", is_final=True))
    version = (await agent.draft_now()).version
    assert await agent.approve(version) is False
    assert agent.update.state == "failed"
    # A stray YES doesn't retry; only an explicit approve of the shown version does.
    assert await agent.handle_control(SignEvent("YES", 1, "control")) is False
    assert await agent.approve(version - 1, "retry") is False
    assert await agent.approve(version, "retry") is True
    assert agent.update.state == "created"
    assert agent.update.key == "SB-9"
    assert jira.request_ids == [jira.request_ids[0]] * 2
    assert await agent.approve(version, "retry") is False


@pytest.mark.asyncio
async def test_notes_are_final_and_in_memory_only():
    notes = CallNotes(ticket_config())
    notes.on_event(Caption("partial", is_final=False))
    notes.on_event(Caption("final caption", is_final=True))
    notes.on_event(OutputSent("mock", "my sentence"))
    assert notes.text() == "them: final caption\nme: my sentence"
    notes.clear()
    assert notes.text() == ""
