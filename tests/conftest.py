import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        help="also run tests marked `live` (real models, APIs, audio devices, webcam)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="live test: run with `uv run pytest --live`")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def vocab_db(tmp_path, monkeypatch):
    """The autocomplete word memory goes to a temporary file, never Application Support."""
    path = tmp_path / "vocab.sqlite"
    monkeypatch.setenv("CALHACKS_VOCAB_DB", str(path))
    return path


@pytest.fixture(autouse=True)
def no_forge(request, monkeypatch):
    """Tests not marked `live` use the mock Jira even when .env has the Forge trigger. The values
    are set empty, not removed, because load_config()'s load_dotenv never overrides a set key."""
    if request.node.get_closest_marker("live") is None:
        for name in ("FORGE_TRIGGER_URL", "FORGE_SHARED_SECRET"):
            monkeypatch.setenv(name, "")
