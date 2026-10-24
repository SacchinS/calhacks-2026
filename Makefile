.PHONY: install swift run mock demo test lint format app demo-reset demo-serve

MAC_APP = ui/macos/.build/debug/SignBridge

install:
	uv sync

# Builds the Mac app's windows (SwiftUI). It launches the Python engine (app.py) itself.
swift:
	swift build --package-path ui/macos

# Opens the app with whatever config.yaml selects.
run: swift
	uv sync -q --inexact
	ENGINE_ROOT=$(CURDIR) $(MAC_APP)

# Opens the app with every component forced to its mock: no webcam, API keys, or BlackHole
# needed. Type mock signs in the control window or in this terminal.
mock: swift
	uv sync -q --inexact
	ENGINE_ROOT=$(CURDIR) $(MAC_APP) --mock

# The live demo: every real component (config.demo.yaml on top of config.yaml).
demo: swift
	uv sync -q --inexact --extra camera
	ENGINE_ROOT=$(CURDIR) $(MAC_APP) --overlay config.demo.yaml

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

# Builds dist/SignBridge.app: the Swift app plus a bundled Python engine (packaging/build.sh).
app:
	packaging/build.sh

# The website Claude Code builds in the demo (claude_code_cli.project_dir): a fresh copy of
# demo/site (the old one is kept as a backup, and Claude Code starts a new session), and a
# local server that reloads the page whenever Claude Code changes a file.
demo-reset:
	uv run python tools/demo_site.py reset

demo-serve:
	uv run python tools/demo_site.py serve
