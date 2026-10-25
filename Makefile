.PHONY: install swift run mock demo test lint format app seed-vocab

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

# Demo words for fingerspelling autocomplete (Julian, Jupyter, June...) in the memory that
# `make demo` and `make mock` use (tools/seed_vocab.py has --synthetic, --time, --list, --reset).
seed-vocab:
	uv run python tools/seed_vocab.py
	uv run python tools/seed_vocab.py --mock
