import subprocess
from pathlib import Path

import pytest

from project_guard.models import PlanSnapshot
from project_guard.reviewer import (
    NotAGitRepoError,
    PlanSnapshotError,
    analyze_diff,
    check_plan_compliance,
    load_plan_snapshot,
)


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


def test_plan_snapshot_json_round_trip(tmp_path):
    snap = PlanSnapshot(
        goal="Add a new response decoder",
        recommended_scope=["pkg/decoder.py"],
        possible_scope=["pkg/client.py"],
        avoid_modifying=["pkg/storage.py"],
        new_dependency="not justified",
        new_abstraction="reuse existing structure",
        refactor="not justified",
    )
    path = tmp_path / "plan.json"
    path.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
    assert load_plan_snapshot(path) == snap


def test_load_plan_snapshot_errors(tmp_path):
    with pytest.raises(PlanSnapshotError):
        load_plan_snapshot(tmp_path / "missing.json")

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(PlanSnapshotError):
        load_plan_snapshot(bad)

    version = tmp_path / "version.json"
    version.write_text('{"version": 2}', encoding="utf-8")
    with pytest.raises(PlanSnapshotError):
        load_plan_snapshot(version)

    missing_field = tmp_path / "missing_field.json"
    missing_field.write_text('{"version": 1, "goal": "x"}', encoding="utf-8")
    with pytest.raises(PlanSnapshotError):
        load_plan_snapshot(missing_field)


def test_plan_compliance_pass(repo):
    plan = PlanSnapshot(
        goal="Add a new response decoder",
        recommended_scope=["app.py"],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_app.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8"
    )
    result = analyze_diff(repo)
    compliance = check_plan_compliance(plan, result)
    assert compliance.status == "PASS"
    assert compliance.risk == "LOW"
    assert compliance.violations == []


def test_plan_compliance_unplanned_production_files(repo):
    plan = PlanSnapshot(
        goal="x",
        recommended_scope=["app.py"],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "models.py").write_text("x = 1\n", encoding="utf-8")
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "WARNING"
    assert compliance.risk == "MEDIUM"
    assert any(
        "Unplanned production file: models.py" in v
        for v in compliance.violations
    )

    (repo / "transport.py").write_text("y = 2\n", encoding="utf-8")
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "VIOLATION"
    assert compliance.risk == "HIGH"


def test_plan_compliance_avoided_file(repo):
    plan = PlanSnapshot(
        goal="x",
        recommended_scope=["app.py"],
        possible_scope=[],
        avoid_modifying=["models.py"],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    (repo / "models.py").write_text("x = 1\n", encoding="utf-8")
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "VIOLATION"
    assert compliance.risk == "HIGH"
    assert any(
        "Modified explicitly avoided file: models.py" in v
        for v in compliance.violations
    )


def test_plan_compliance_dependency_conflict(repo):
    plan = PlanSnapshot(
        goal="x",
        recommended_scope=[],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    (repo / "requirements.txt").write_text(
        "requests==2.31\n", encoding="utf-8"
    )
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "WARNING"
    assert compliance.risk == "MEDIUM"
    assert any(
        "Dependency file changed" in v for v in compliance.violations
    )


def test_plan_compliance_refactor_signal(repo):
    plan = PlanSnapshot(
        goal="x",
        recommended_scope=[],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        (repo / name).write_text(f"# {name}\n", encoding="utf-8")
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "VIOLATION"
    assert compliance.risk == "HIGH"
    assert any(
        "Possible unplanned refactor" in v for v in compliance.violations
    )
