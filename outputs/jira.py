"""The engine-side Jira boundary.

The Mac never receives a Jira token.  In production this client sends one HMAC-signed
request to the Forge web trigger; the Forge app performs all Jira REST calls as the app.
When the trigger variables are absent, the deterministic mock keeps the demo and tests
offline.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from shared.config import Config

log = logging.getLogger(__name__)


class JiraError(RuntimeError):
    """A sanitized bridge failure; request bodies are never included."""


class JiraClient:
    def __init__(self, config: Config, opener: Any = None) -> None:
        self.config = config
        self.url = str(Config.secret("FORGE_TRIGGER_URL") or "").strip()
        self.secret = str(Config.secret("FORGE_SHARED_SECRET") or "")
        self._opener = opener or urllib.request.urlopen
        self.mock = not (self.url and self.secret)
        self._mock_number = 0

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("tickets.enabled", False))

    async def context(self, summary: str, terms: list[str]) -> dict[str, list[dict[str, Any]]]:
        if self.mock:
            return {"similar": [], "release": []}
        return await self._post({"action": "context", "summary": summary, "terms": terms})

    async def create(self, ticket: Any, audit: dict[str, Any]) -> dict[str, Any]:
        request_id = f"{audit.get('call_id', uuid.uuid4().hex)}-v{audit.get('draft_version', 1)}"
        payload = {
            "action": "create",
            "request_id": request_id,
            "ticket": {
                "summary": ticket.summary,
                "description": ticket.description,
                "due": ticket.due,
                "labels": list(ticket.labels),
                "assign_to_signer": bool(ticket.assign_to_signer),
                "blocks": ticket.blocks or "",
            },
            "audit": audit,
        }
        if self.mock:
            self._mock_number += 1
            key = f"MOCK-{self._mock_number}"
            return {
                "key": key,
                "url": f"https://mock.invalid/browse/{key}",
                "linked": ticket.blocks or None,
                "audit_saved": True,
                "warnings": [],
                "mock": True,
            }
        return await self._post(payload)

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret.encode("utf-8"), timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-SignBridge-Timestamp": timestamp,
                "X-SignBridge-Signature": signature,
            },
        )

        def send() -> tuple[int, bytes]:
            try:
                with self._opener(request, timeout=20) as response:
                    return int(response.status), response.read()
            except urllib.error.HTTPError as exc:
                return int(exc.code), exc.read()
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise JiraError(f"Forge request failed: {type(exc).__name__}") from None

        status, raw = await asyncio.to_thread(send)
        if status < 200 or status >= 300:
            raise JiraError(f"Forge returned HTTP {status}")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise JiraError("Forge returned invalid JSON") from None
        if not isinstance(result, dict):
            raise JiraError("Forge returned an invalid result")
        return result
