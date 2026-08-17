import tomllib
from pathlib import Path

import project_guard


def test_package_version_matches_pyproject():
    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert project["version"] == project_guard.__version__
