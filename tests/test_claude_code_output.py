"""The real Claude Code output, driven against a fake `claude` that prints stream-json."""

import json
import sys
import textwrap

import pytest

from outputs.claude_code import ClaudeCodeOutput, describe_tool
from shared.bus import Bus
from shared.config import Config
from shared.events import OutputReply

FAKE_CLAUDE = textwrap.dedent(
    """\
    #!{python}
    import json, sys
    with open("args.jsonl", "a") as f:
        f.write(json.dumps(sys.argv[1:]) + "\\n")
    text = sys.argv[sys.argv.index("-p") + 1]
    def out(event):
        print(json.dumps(event), flush=True)
    out({{"type": "system", "subtype": "init", "session_id": "sess-1"}})
    out({{"type": "assistant", "session_id": "sess-1", "message": {{"content": [
        {{"type": "tool_use", "name": "Write", "input": {{"file_path": "/x/index.html"}}}}]}}}})
    out({{"type": "assistant", "session_id": "sess-1", "message": {{"content": [
        {{"type": "text", "text": "Built it."}}]}}}})
    fail = text == "fail"
    out({{"type": "result", "subtype": "success", "is_error": fail,
         "result": "boom" if fail else "ok", "session_id": "sess-1"}})
    sys.exit(1 if fail else 0)
    """
)


@pytest.fixture
def site(tmp_path):
    claude = tmp_path / "claude"
    claude.write_text(FAKE_CLAUDE.format(python=sys.executable))
    claude.chmod(0o755)
    project = tmp_path / "site"
    project.mkdir()
    config = Config(
        sections={"claude_code_cli": {"command": str(claude), "project_dir": str(project)}}
    )
    return config, project


def calls(project):
    return [json.loads(line) for line in (project / "args.jsonl").read_text().splitlines()]


async def test_streams_the_reply_and_resumes_the_same_session(site):
    config, project = site
    bus = Bus()
    replies = bus.subscribe(OutputReply)
    output = ClaudeCodeOutput(bus, config)
    assert output.available()

    await output.send("Build a website for a grocery store.")
    chunks = []
    while not replies.queue.empty():
        chunks.append(replies.get_nowait())
    assert [c.text for c in chunks[:2]] == ["Writing index.html…", "Built it."]
    assert chunks[-1].done and chunks[-1].text.startswith("Done in")

    await output.send("Make the title red.")
    first, second = calls(project)
    assert "--resume" not in first
    assert second[second.index("--resume") + 1] == "sess-1"
    for args in (first, second):
        assert args[args.index("--permission-mode") + 1] == "acceptEdits"
        assert args[args.index("--allowedTools") + 1] == "Read,Edit,Write,Glob,Grep"
        assert "--dangerously-skip-permissions" not in args and "--add-dir" not in args
        assert "--continue" not in args

    # A restart keeps the session (it's remembered in the project folder).
    assert ClaudeCodeOutput(bus, config).session_id == "sess-1"
    output.new_session()
    assert ClaudeCodeOutput(bus, config).session_id is None


async def test_a_failed_run_raises_so_the_router_falls_back(site):
    config, _ = site
    bus = Bus()
    replies = bus.subscribe(OutputReply)
    with pytest.raises(RuntimeError, match="boom"):
        await ClaudeCodeOutput(bus, config).send("fail")
    chunks = []
    while not replies.queue.empty():
        chunks.append(replies.get_nowait())
    assert chunks[-1].done


def test_unavailable_without_the_project_folder(tmp_path):
    config = Config(sections={"claude_code_cli": {"project_dir": str(tmp_path / "missing")}})
    assert not ClaudeCodeOutput(Bus(), config).available()


def test_tool_descriptions():
    assert describe_tool("Edit", {"file_path": "/a/b/style.css"}) == "Editing style.css…"
    assert describe_tool("Glob", {"pattern": "*.html"}) == "Glob *.html…"
