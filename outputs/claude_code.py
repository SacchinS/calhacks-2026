"""Sends text to the real Claude Code CLI, headless, in the demo project folder.

    claude -p "<text>" --output-format stream-json --verbose
           --permission-mode acceptEdits --allowedTools Read,Edit,Write,Glob,Grep
           [--resume <session id>]

Its reply streams back to the UI as OutputReply chunks: what it says, and each file it
touches. Every request after the first continues the same session with `--resume <id>`
(read from the stream), so the demo's re-prompt edits what the kick-off built. Rather than
`--continue`, which picks the folder's latest session and any other `claude` run there
would change.

Permissions: acceptEdits plus a short --allowedTools list, so a minutes-long build never
stops for an approval nobody can answer. Never --dangerously-skip-permissions, and no
--add-dir: Claude Code runs with project_dir as its working directory and stays inside it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from outputs.base import Output
from shared.bus import Bus
from shared.config import Config
from shared.events import OutputReply

log = logging.getLogger(__name__)

DEFAULT_TOOLS = "Read,Edit,Write,Glob,Grep"


class ClaudeCodeOutput(Output):
    name = "claude_code"

    def __init__(self, bus: Bus, config: Config) -> None:
        super().__init__(bus, config)
        self.command = config.get("claude_code_cli.command", "claude")
        self.project_dir = config.path("claude_code_cli.project_dir", "../demo-site")
        self.allowed_tools = config.get("claude_code_cli.allowed_tools", DEFAULT_TOOLS)
        self.model = config.get("claude_code_cli.model", "") or None
        self.timeout = float(config.get("claude_code_cli.timeout_seconds", 900))
        # The session to continue; remembered on disk so a restart mid-demo keeps it.
        self.session_file = self.project_dir / ".claude-session"
        self.session_id: str | None = self._load_session()

    def available(self) -> bool:
        return shutil.which(self.command) is not None and self.project_dir.is_dir()

    def new_session(self) -> None:
        """Forget the session: the next request starts fresh (e.g. after resetting the site)."""
        self.session_id = None
        with contextlib.suppress(OSError):
            self.session_file.unlink()

    def args(self, text: str) -> list[str]:
        args = [self.command, "-p", text, "--output-format", "stream-json", "--verbose"]
        args += ["--permission-mode", "acceptEdits", "--allowedTools", self.allowed_tools]
        if self.model:
            args += ["--model", self.model]
        if self.session_id:
            args += ["--resume", self.session_id]
        return args

    async def send(self, text: str) -> None:
        self.session_id = self._load_session()  # `tools/demo_site.py reset` starts a fresh one
        log.info("Claude Code request (%d chars), session %s", len(text), self.session_id)
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *self.args(text),
            cwd=self.project_dir,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,  # stream-json lines can carry whole files
        )
        result: dict[str, Any] | None = None
        try:
            async with asyncio.timeout(self.timeout):
                assert proc.stdout is not None
                async for raw in proc.stdout:
                    event = parse(raw)
                    if event is None:
                        continue
                    self._remember_session(event.get("session_id"))
                    for chunk in reply_chunks(event):
                        self.bus.publish(OutputReply(self.name, chunk))
                    if event.get("type") == "result":
                        result = event
                stderr = await proc.stderr.read() if proc.stderr else b""
                code = await proc.wait()
        except BaseException:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            self.bus.publish(OutputReply(self.name, "Claude Code stopped.", done=True))
            raise

        seconds = time.monotonic() - started
        if code != 0 or result is None or result.get("is_error"):
            detail = (result or {}).get("result") or stderr.decode(errors="replace").strip()
            self.bus.publish(OutputReply(self.name, "Claude Code failed.", done=True))
            raise RuntimeError(f"Claude Code exited {code}: {detail[-300:]}")
        self.bus.publish(OutputReply(self.name, f"Done in {seconds:.0f} s.", done=True))

    def _remember_session(self, session_id: Any) -> None:
        if isinstance(session_id, str) and session_id and session_id != self.session_id:
            self.session_id = session_id
            with contextlib.suppress(OSError):
                self.session_file.write_text(session_id)

    def _load_session(self) -> str | None:
        try:
            return self.session_file.read_text().strip() or None
        except OSError:
            return None


def parse(raw: bytes) -> dict[str, Any] | None:
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def reply_chunks(event: dict[str, Any]) -> list[str]:
    """What to show from one stream-json event: Claude's text and the files it works on."""
    if event.get("type") != "assistant":
        return []
    chunks = []
    for block in event.get("message", {}).get("content", []):
        if block.get("type") == "text" and block.get("text", "").strip():
            chunks.append(block["text"].strip())
        elif block.get("type") == "tool_use":
            chunks.append(describe_tool(block.get("name", ""), block.get("input") or {}))
    return chunks


def describe_tool(name: str, args: dict[str, Any]) -> str:
    target = args.get("file_path") or args.get("path") or args.get("pattern") or ""
    if target:
        target = Path(str(target)).name if "file_path" in args else str(target)
    verb = {"Write": "Writing", "Edit": "Editing", "Read": "Reading"}.get(name, name)
    return f"{verb} {target}".strip() + "…"
