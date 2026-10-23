"""Contract for Translator: every implementation must pass this.

The Claude translator calls the real API, so it only runs with `pytest --live`.
"""

import pytest

from app import load_class
from language.base import Translator
from shared.events import Translation
from tests.contracts.conftest import live

GLOSSES = [
    ["ME", "WANT", "FIX", "BUG", "LOGIN", "PAGE"],
    ["MAKE", "fs-TITLE", "RED"],
    ["HELLO"],
]


@pytest.mark.parametrize("name", ["mock", live("claude")])
@pytest.mark.parametrize("gloss", GLOSSES, ids=" ".join)
async def test_translator_contract(name, gloss, config):
    translator = load_class("translator", name)(config)
    assert isinstance(translator, Translator)
    result = await translator.translate(list(gloss))
    assert isinstance(result, Translation)
    assert result.gloss == gloss
    assert result.english.strip()
    assert result.provider == translator.provider
    assert "fs-" not in result.english
