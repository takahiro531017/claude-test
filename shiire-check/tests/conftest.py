import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from shiire_check.config import DEFAULTS, _merge  # noqa: E402


@pytest.fixture
def cfg():
    return _merge(DEFAULTS, {"workers": 2})


@pytest.fixture(scope="session")
def dummy(tmp_path_factory):
    import make_dummy_data

    return make_dummy_data.generate(tmp_path_factory.mktemp("dummy"))
