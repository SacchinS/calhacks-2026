"""Loads config.yaml plus secrets from .env (ANTHROPIC_API_KEY, CARTESIA_API_KEY)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from shared.events import MODES

ROOT = Path(__file__).resolve().parent.parent  # the repo, or Resources/engine in the .app

# Allowed values for each component line. The first one is the mock.
CHOICES: dict[str, tuple[str, ...]] = {
    "recognizer": ("mock", "replay", "camera"),
    "translator": ("mock", "claude"),
    "claude_code": ("mock", "real"),
    "tts": ("mock", "say", "cartesia"),
    "captions": ("mock", "cartesia"),
}


@dataclass
class Config:
    recognizer: str = "mock"
    translator: str = "mock"
    claude_code: str = "mock"
    tts: str = "mock"
    captions: str = "mock"
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


def load_config(path: str | Path | None = None, **overrides: str) -> Config:
    load_dotenv(ROOT / ".env")
    path = Path(path) if path else ROOT / "config.yaml"
    raw: dict[str, Any] = (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}
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
