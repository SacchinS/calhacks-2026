.PHONY: install run mock test lint format app

install:
	uv sync

# Runs with whatever config.yaml selects.
run:
	uv run python app.py

# Opens both windows with every component forced to its mock: no webcam, API keys, or
# BlackHole needed.
mock:
	uv run python app.py --mock

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

# Builds dist/calhacks-2026.app with PyInstaller (see packaging/app.spec).
app:
	uv run pyinstaller packaging/app.spec --noconfirm --distpath dist --workpath build
