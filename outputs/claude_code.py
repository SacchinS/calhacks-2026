"""Sends text to the real Claude Code CLI. STUB: unavailable, so the router uses the console."""

from __future__ import annotations

import logging

from outputs.base import Output
from shared.bus import Bus
from shared.config import Config

log = logging.getLogger(__name__)


class ClaudeCodeOutput(Output):
    name = "claude_code"

    def __init__(self, bus: Bus, config: Config) -> None:
        super().__init__(bus, config)
        self.command = config.get("claude_code_cli.command", "claude")
        self.project_dir = config.path("claude_code_cli.project_dir", "../demo-site")
        log.warning("ClaudeCodeOutput is a stub: requests go to the console")

    def available(self) -> bool:
        # TODO(Person B): return shutil.which(self.command) is not None and
        # self.project_dir.is_dir().
        return False

    async def send(self, text: str) -> None:
        # TODO(Person B): run Claude Code headless in the demo project and stream its reply:
        #   proc = await asyncio.create_subprocess_exec(
        #       self.command, "-p", text, "--output-format", "stream-json", "--verbose",
        #       cwd=self.project_dir, stdout=PIPE, stderr=PIPE)
        #   for each line of stdout: parse the JSON, pull out assistant text, and
        #   self.bus.publish(OutputReply(self.name, chunk)); finish with done=True.
        # Raise if the exit code is non-zero. Pick the --permission-mode / --allowedTools
        # the demo needs so edits don't stop for an approval prompt nobody can answer.
        raise NotImplementedError("ClaudeCodeOutput is a stub")
