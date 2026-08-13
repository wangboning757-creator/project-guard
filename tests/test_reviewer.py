import subprocess
from pathlib import Path

import pytest

from project_guard.reviewer import NotAGitRepoError, analyze_diff


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    return tmp_path


def test_review_small_change_is_low(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    result = analyze_diff(repo)
    assert result.changed_files == 1
    assert result.total_added == 1
    assert result.risk == "LOW"


def test_review_large_diff_is_high(repo):
    (repo / "new_module.py").write_text(
        "x = 1\n" * 1100, encoding="utf-8"
    )
    result = analyze_diff(repo)
    assert result.added_files == 1
    assert result.risk == "HIGH"
    assert result.large_file_additions


def test_review_dependency_change_is_medium(repo):
    (repo / "requirements.txt").write_text(
        "requests==2.31\n", encoding="utf-8"
    )
    result = analyze_diff(repo)
    assert result.dependency_changed
    assert result.risk == "MEDIUM"


def test_review_not_git(tmp_path):
    with pytest.raises(NotAGitRepoError):
        analyze_diff(tmp_path)
