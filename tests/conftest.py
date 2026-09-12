import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from nbaplayin import build, model, sensitivity  # noqa: E402


@pytest.fixture(scope="session")
def study():
    return build.load_study()


@pytest.fixture(scope="session")
def solved(study):
    return sensitivity.exact_results(study)
