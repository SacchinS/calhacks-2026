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
