"""Loads config.yaml plus secrets from .env (ANTHROPIC_API_KEY, CARTESIA_API_KEY).

Secrets come from the repo's .env, then ~/Library/Application Support/calhacks-2026/.env
(where the packaged app gets them; keys never go in the bundle or the repo). The packaged
app also prefers a config.yaml in that folder, so it can run real components even though
the bundled config.yaml keeps every line on mock.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from shared.events import MODES

ROOT = Path(__file__).resolve().parent.parent  # the repo, or Resources/engine in the .app
SUPPORT = Path("~/Library/Application Support/calhacks-2026").expanduser()
IN_APP_BUNDLE = ".app/Contents/Resources" in str(ROOT)

# Allowed values for each component line. The first one is the mock.
CHOICES: dict[str, tuple[str, ...]] = {
    "recognizer": ("mock", "replay", "camera"),
    "translator": ("mock", "claude"),
    "claude_code": ("mock", "real"),
    "siri": ("mock", "real"),
    "tts": ("mock", "say", "cartesia"),
    "captions": ("mock", "cartesia"),
    "vocab_search": ("mock", "moss"),
}


@dataclass
class Config:
    recognizer: str = "mock"
    translator: str = "mock"
    claude_code: str = "mock"
    siri: str = "mock"
    tts: str = "mock"
    captions: str = "mock"
    vocab_search: str = "mock"
    mode: str = "claude_code"
    # Every other section of config.yaml (ui, recognition, language, audio, ...), as dicts.
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)

    def section(self, name: str) -> dict[str, Any]:
        return self.sections.get(name) or {}

    def get(self, dotted: str, default: Any = None) -> Any:
        """`cfg.get("audio.virtual_mic_device")`"""
        name, _, key = dotted.partition(".")
        return self.section(name).get(key, default)

    def path(self, dotted: str, default: str = "") -> Path:
        """A config value as a path, resolved against the repo root."""
        p = Path(self.get(dotted, default))
        return p if p.is_absolute() else ROOT / p

    def all_mocks(self) -> Config:
        """A copy with every component line set to its mock (what `make mock` runs)."""
        mocks = {key: values[0] for key, values in CHOICES.items()}
        return Config(**mocks, mode=self.mode, sections=self.sections)

    @staticmethod
    def secret(name: str) -> str | None:
        return os.environ.get(name) or None


def merge(base: dict[str, Any], top: dict[str, Any]) -> dict[str, Any]:
    """`top` over `base`, merging sections key by key."""
    out = dict(base)
    for key, value in top.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **value}
        else:
            out[key] = value
    return out


def load_config(
    path: str | Path | None = None, overlay: str | Path | None = None, **overrides: str
) -> Config:
    """config.yaml, then `overlay` on top (e.g. config.demo.yaml), then `overrides`."""
    load_dotenv(ROOT / ".env")
    load_dotenv(SUPPORT / ".env")  # doesn't override keys already set
    if path is None and IN_APP_BUNDLE and (SUPPORT / "config.yaml").exists():
        path = SUPPORT / "config.yaml"
    path = Path(path) if path else ROOT / "config.yaml"
    raw: dict[str, Any] = (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}
    if overlay is not None:
        overlay = Path(overlay) if Path(overlay).is_absolute() else ROOT / overlay
        raw = merge(raw, yaml.safe_load(overlay.read_text()) or {})
    raw.update(overrides)

    lines = {key: str(raw.pop(key, values[0])) for key, values in CHOICES.items()}
    for key, value in lines.items():
        if value not in CHOICES[key]:
            raise ValueError(f"config.yaml: {key}: {value!r} is not one of {CHOICES[key]}")
    mode = str(raw.pop("mode", "claude_code"))
    if mode not in MODES:
        raise ValueError(f"config.yaml: mode: {mode!r} is not one of {MODES}")
    sections = {k: v for k, v in raw.items() if isinstance(v, dict)}
    return Config(**lines, mode=mode, sections=sections)
