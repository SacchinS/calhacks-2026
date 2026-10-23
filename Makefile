.PHONY: install swift run mock test lint format app

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
