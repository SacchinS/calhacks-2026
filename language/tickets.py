"""In-memory live ticket drafting and approval.

The agent is deliberately separate from the event types in ``shared/``.  Captions and
spoken output are retained only in this process; nothing is sent to Forge until the
signer approves the exact ready version with YES (or the UI confirm action).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from outputs.jira import JiraClient, JiraError
from shared.bus import Bus
from shared.config import Config
from shared.events import Caption, Mention, Notice, OutputSent, SignEvent

log = logging.getLogger(__name__)

LABEL = re.compile(r"^[a-z0-9-]{1,40}$")

SYSTEM = """You keep one tentative Jira work ticket up to date during a live meeting.
Propose a concrete task as soon as one appears. Update the current wording only when new
conversation adds an owner, date, decision, dependency or important detail. `ready` is true
only after someone has asked the signer to do it and the signer has agreed or committed.
Never invent work, people or dates; resolve relative dates against today. Use remembered
spellings for names and tools. Never quote a speaker verbatim. Return JSON matching the schema.
"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticket": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "description": {"type": "string"},
                        "asked": {"type": "string"},
                        "due": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                        "people": {"type": "array", "items": {"type": "string"}},
                        "assign_to_signer": {"type": "boolean"},
                        "ready": {"type": "boolean"},
                        "reasons": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "summary",
                        "description",
                        "asked",
                        "due",
                        "labels",
                        "people",
                        "assign_to_signer",
                        "ready",
                        "reasons",
                    ],
                    "additionalProperties": False,
                },
            ]
        }
    },
    "required": ["ticket"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class TicketDraft:
    summary: str
    description: str
    asked: str = ""
    due: str = ""
    labels: tuple[str, ...] = ()
    people: tuple[str, ...] = ()
    assign_to_signer: bool = False
    ready: bool = False
    reasons: tuple[str, ...] = ()
    blocks: str = ""
    related: tuple[dict[str, Any], ...] = ()
    possible_duplicate: dict[str, Any] | None = None
    words: tuple[dict[str, Any], ...] = ()

    def public(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "description": self.description,
            "asked": self.asked,
            "assignee": "signer" if self.assign_to_signer else "",
            "due": self.due,
            "labels": list(self.labels),
            "people": list(self.people),
            "reasons": list(self.reasons),
            "blocks": next((x for x in self.related if x.get("key") == self.blocks), None)
            if self.blocks
            else None,
            "possible_duplicate": self.possible_duplicate,
            "words": list(self.words),
        }


@dataclass(frozen=True)
class TicketUpdate:
    state: str
    version: int = 0
    ready: bool = False
    changed: tuple[str, ...] = ()
    draft: TicketDraft | None = None
    jira: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {"similar": [], "release": []}
    )
    announce: str = ""
    key: str = ""
    url: str = ""
    linked: str | None = None
    audit_saved: bool = False
    warnings: tuple[str, ...] = ()
    error: str = ""
    mock: bool = False
    draft_ms: int | None = None
    create_ms: int | None = None

    def public(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "version": self.version,
            "ready": self.ready,
            "changed": list(self.changed),
            "draft": self.draft.public() if self.draft else None,
            "jira": self.jira,
            "announce": self.announce,
            "key": self.key,
            "url": self.url,
            "linked": self.linked,
            "audit_saved": self.audit_saved,
            "warnings": list(self.warnings),
            "error": self.error,
            "mock": self.mock,
            "draft_ms": self.draft_ms,
            "create_ms": self.create_ms,
        }


class CallNotes:
    """Final captions and our sent sentences, held in memory only."""

    def __init__(self, config: Config) -> None:
        self.maxlen = int(config.get("tickets.notes_max", 400))
        self.entries: deque[tuple[float, str, str]] = deque(maxlen=self.maxlen)

    def on_event(self, event: Any) -> None:
        if isinstance(event, Caption) and event.is_final and event.text.strip():
            self.entries.append((event.ts, "them", event.text.strip()))
        elif isinstance(event, OutputSent) and event.text.strip():
            self.entries.append((event.ts, "me", event.text.strip()))

    def text(self) -> str:
        return "\n".join(f"{speaker}: {text}" for _, speaker, text in self.entries)

    def clear(self) -> None:
        self.entries.clear()


def _clean_draft(raw: Any) -> TicketDraft | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("ticket is not an object")
    summary = " ".join(str(raw.get("summary", "")).split())
    description = " ".join(str(raw.get("description", "")).split())
    asked = " ".join(str(raw.get("asked", "")).split())
    due = str(raw.get("due", "")).strip()
    if not summary or len(summary) > 120 or not description or len(description) > 2000:
        raise ValueError("ticket text is out of bounds")
    if due:
        try:
            date.fromisoformat(due)
        except ValueError:
            raise ValueError("invalid due date") from None
    labels = tuple(dict.fromkeys(str(x).lower() for x in raw.get("labels", []) if str(x)))
    if len(labels) > 3 or any(not LABEL.fullmatch(x) for x in labels):
        raise ValueError("invalid labels")
    people = tuple(dict.fromkeys(" ".join(str(x).split()) for x in raw.get("people", []) if str(x)))
    reasons = tuple(" ".join(str(x).split())[:240] for x in raw.get("reasons", []) if str(x))[:3]
    return TicketDraft(
        summary=summary,
        description=description,
        asked=asked[:160],
        due=due,
        labels=labels,
        people=people[:12],
        assign_to_signer=bool(raw.get("assign_to_signer", False)),
        ready=bool(raw.get("ready", False)),
        reasons=reasons,
    )


class TicketDrafter:
    def __init__(self, config: Config, client: Any = None, notice_bus: Bus | None = None) -> None:
        self.config = config
        self.model = str(config.get("tickets.model", "claude-opus-5-5"))
        self.effort = str(config.get("tickets.effort", "low"))
        self._client = client
        self.notice_bus = notice_bus

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(timeout=15, max_retries=1)
        return self._client

    async def draft(
        self,
        notes_text: str,
        current: TicketDraft | None,
        dismissed: list[str],
        words: list[dict[str, Any]],
        today: str | None = None,
        signer: str = "",
        jira: dict[str, Any] | None = None,
    ) -> TicketDraft | None:
        payload = {
            "today": today or date.today().isoformat(),
            "signer": signer,
            "notes": notes_text,
            "current_ticket": current.public() if current else None,
            "dismissed": dismissed,
            "remembered_words": words,
            "jira_context": jira or {"similar": [], "release": []},
        }
        kwargs: dict[str, Any] = {
            "model": self.model,
            # Opus 5.5 always thinks, and thinking counts toward this: room for both, so a
            # long draft isn't cut off mid-JSON (which would silently drop the ticket).
            "max_tokens": 16000,
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
            "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        }
        try:
            if "haiku" in self.model.lower():
                kwargs["thinking"] = {"type": "disabled"}
                response = await self.client.messages.create(**kwargs)
            else:
                response = await self.client.beta.messages.create(
                    **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            if getattr(response, "stop_reason", "") == "refusal":
                raise ValueError("Claude refused the ticket draft")
            text = "".join(
                str(block.text)
                for block in getattr(response, "content", [])
                if getattr(block, "type", "") == "text"
            )
            parsed = json.loads(text)
            return _clean_draft(parsed.get("ticket") if isinstance(parsed, dict) else None)
        except Exception as exc:
            if self.notice_bus is not None:
                self.notice_bus.publish(
                    Notice("warning", "Ticket draft unavailable; no Jira action proposed")
                )
            log.debug("ticket draft rejected: %s", type(exc).__name__)
            return None


def _changed(before: TicketDraft | None, after: TicketDraft) -> tuple[str, ...]:
    if before is None:
        return ("summary", "description", "due", "labels", "assignee", "reasons")
    fields = (
        "summary",
        "description",
        "asked",
        "due",
        "labels",
        "assign_to_signer",
        "ready",
        "reasons",
        "blocks",
    )
    return tuple(name for name in fields if getattr(before, name) != getattr(after, name))


class TicketAgent:
    def __init__(
        self,
        bus: Bus,
        config: Config,
        jira: JiraClient,
        drafter: TicketDrafter | None = None,
        autocomplete: Any = None,
        announcer: Any = None,
    ) -> None:
        self.bus = bus
        self.config = config
        self.enabled = bool(config.get("tickets.enabled", False))
        self.jira = jira
        self.drafter = drafter or TicketDrafter(config, notice_bus=bus)
        self.autocomplete = autocomplete
        self.announcer = announcer
        self.notes = CallNotes(config)
        # Who "the signer" is, for Claude and the audit: Settings > Calls sets it (ui/server.py).
        self.signer = str(config.get("meet.signer_name", "") or "")
        self.update = TicketUpdate("none")
        self.dismissed: list[str] = []
        self.history: list[dict[str, Any]] = []
        self.call_id = f"call-{uuid.uuid4().hex[:12]}"
        self._sub = None
        self._task: asyncio.Task[None] | None = None
        self._draft_task: asyncio.Task[None] | None = None
        self._dirty = False

    @property
    def current(self) -> TicketDraft | None:
        return self.update.draft

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._sub = self.bus.subscribe(Caption, OutputSent, Mention)
        self._task = asyncio.create_task(self._run(), name="ticket-agent")

    async def stop(self) -> None:
        if self._draft_task is not None:
            self._draft_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._draft_task
            self._draft_task = None
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._sub is not None:
            self._sub.close()
            self._sub = None

    async def _run(self) -> None:
        try:
            async for event in self._sub:
                self.notes.on_event(event)
                if isinstance(event, (OutputSent, Mention)):
                    self._schedule()
                elif (
                    isinstance(event, Caption)
                    and event.is_final
                    and self.update.state == "tentative"
                ):
                    self._schedule()
        finally:
            if self._sub is not None:
                self._sub.close()

    def _schedule(self) -> None:
        if not self.enabled or self.update.state in ("creating", "created"):
            return
        self._dirty = True
        if self._draft_task is None or self._draft_task.done():
            self._draft_task = asyncio.create_task(self._settled_draft(), name="ticket-draft")

    async def _settled_draft(self) -> None:
        while self._dirty:
            self._dirty = False
            await asyncio.sleep(float(self.config.get("tickets.settle_seconds", 3)))
            await self.draft_now()

    async def draft_now(self) -> TicketUpdate:
        if not self.enabled or self.update.state in ("creating", "created"):
            return self.update
        notes = self.notes.text()
        if not notes.strip():
            return self.update
        started = time.monotonic()
        words: list[dict[str, Any]] = []
        if self.autocomplete is not None and hasattr(self.autocomplete, "related_words"):
            with contextlib.suppress(Exception):
                words = await self.autocomplete.related_words(notes, k=8)
        try:
            context = await self.jira.context(
                # Never send captions to Forge. Before the first draft there is no safe
                # summary yet, so use a constant query and only the remembered terms.
                self.current.summary if self.current else "meeting action",
                [w.get("term", "") for w in words],
            )
            draft = await self.drafter.draft(
                notes,
                self.current,
                self.dismissed,
                words,
                today=date.today().isoformat(),
                signer=self.signer,
                jira=context,
            )
        except Exception as exc:
            self.bus.publish(Notice("warning", "Ticket draft unavailable; no Jira action proposed"))
            log.debug("ticket draft failed: %s", type(exc).__name__)
            return self.update
        if draft is None:
            return self.update
        release = context.get("release", [])
        related = tuple(x for x in release[:3] if isinstance(x, dict) and x.get("key"))
        if related and not draft.blocks:
            draft = replace(
                draft,
                related=related,
                # Once the signer has approved the owner/action, the first open release
                # issue becomes the explicit dependency sent to Forge.
                blocks=related[0]["key"] if draft.ready else "",
            )
        elif related:
            draft = replace(draft, related=related)
        version = self.update.version + 1
        changed = _changed(self.current, draft)
        self.history.append(
            {
                "version": version,
                "changed": list(changed),
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        self.update = TicketUpdate(
            state="tentative",
            version=version,
            ready=draft.ready,
            changed=changed,
            draft=draft,
            jira=context,
            announce=str(
                self.config.get("tickets.announce_text", "I've added it to Jira as {key}.")
            ),
            mock=self.jira.mock,
            draft_ms=round((time.monotonic() - started) * 1000),
        )
        self.bus.publish(self.update)
        return self.update

    async def handle_control(self, event: SignEvent) -> bool:
        if self.update.state != "tentative" or self.update.draft is None:
            return False
        if event.gloss == "NO":
            self.dismiss()
            return True
        if event.gloss == "YES":
            if self.update.ready:
                await self.approve(self.update.version, "signed YES")
            return True
        return False

    async def approve(self, version: int, via: str = "button") -> bool:
        # A failed create can be retried with the same version (and so the same Forge request_id).
        if (
            self.update.state not in ("tentative", "failed")
            or self.update.draft is None
            or not self.update.ready
            or version != self.update.version
        ):
            return False
        draft = self.update.draft
        self.update = replace(self.update, state="creating", changed=())
        self.bus.publish(self.update)
        started = time.monotonic()
        audit = {
            "call_id": self.call_id,
            "draft_version": version,
            "approved_by": self.signer or "signer",
            "approved_via": via,
            "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": self.drafter.model,
            "reasons": list(draft.reasons),
            "versions": list(self.history),
        }
        try:
            result = await self.jira.create(draft, audit)
        except JiraError as exc:
            self.update = replace(
                self.update,
                state="failed",
                error=str(exc),
                create_ms=round((time.monotonic() - started) * 1000),
            )
            self.bus.publish(self.update)
            return False
        key = str(result.get("key", ""))
        self.update = replace(
            self.update,
            state="created",
            key=key,
            url=str(result.get("url", "")),
            linked=result.get("linked"),
            audit_saved=bool(result.get("audit_saved", False)),
            warnings=tuple(str(x) for x in result.get("warnings", [])),
            mock=bool(result.get("mock", self.jira.mock)),
            create_ms=round((time.monotonic() - started) * 1000),
        )
        self.bus.publish(self.update)
        if self.announcer is not None and key:
            with contextlib.suppress(Exception):
                await self.announcer.announce(self.update.announce.format(key=key))
        return True

    def dismiss(self) -> None:
        if self.update.draft is not None:
            self.dismissed.append(self.update.draft.summary)
        self.update = TicketUpdate("dismissed", version=self.update.version)
        self.bus.publish(self.update)
        self.update = TicketUpdate("none", version=self.update.version)
        self.bus.publish(self.update)

    def clear_notes(self) -> None:
        self.notes.clear()
        self.dismissed.clear()
        self.update = TicketUpdate("none", version=self.update.version)
        self.bus.publish(self.update)
