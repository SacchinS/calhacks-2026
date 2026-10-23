import pytest

from shared.bus import Bus
from shared.config import load_config


@pytest.fixture
def config():
    return load_config().all_mocks()


@pytest.fixture
def bus():
    return Bus()


def live(*values):
    """Parametrize values for a real implementation: runs only with `pytest --live`."""
    return pytest.param(*values, marks=pytest.mark.live, id="-".join(values))
