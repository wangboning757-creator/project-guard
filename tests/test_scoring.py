from project_guard.models import ReviewResult, ScanResult
from project_guard.scanner import scan_project
from project_guard.scoring import compute_score


def test_score_clean_project_is_100(tmp_path):
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    result = compute_score(scan_project(tmp_path))
    assert result.score == 100


def test_score_penalties(tmp_path):
    (tmp_path / "huge.py").write_text("x = 1\n" * 900, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(
        "\n".join(f"pkg{i}" for i in range(20)), encoding="utf-8"
    )
    scan = scan_project(tmp_path)
    result = compute_score(scan)
    assert result.score < 100
    rules = [d.rule for d in result.deductions]
    assert "giant file" in rules
    assert "dependency count" in rules
    assert "missing README" in rules


def test_score_large_diff_penalty(tmp_path):
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    scan = scan_project(tmp_path)
    review = ReviewResult(
        changed_files=1,
        added_files=1,
        deleted_files=0,
        total_added=1200,
        total_deleted=0,
        dependency_changed=False,
        risk="HIGH",
        reasons=["very large diff (+1200 lines)"],
    )
    result = compute_score(scan, review)
    assert result.score == 85
    assert any(d.rule == "large diff" and d.points == 15 for d in result.deductions)


def test_score_common_filenames_across_dirs_are_not_penalized(tmp_path):
    for name in ("llm", "search"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "base.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / name / "mock.py").write_text("x = 1\n", encoding="utf-8")
    result = compute_score(scan_project(tmp_path))
    assert not any(
        d.rule == "duplicate module name" for d in result.deductions
    )


def test_score_size_penalties_ignore_non_source_files(tmp_path):
    (tmp_path / "huge.py").write_text("x = 1\n" * 900, encoding="utf-8")
    (tmp_path / "fixture.json").write_text("{}\n" * 900, encoding="utf-8")
    (tmp_path / "image.png").write_text("x\n" * 900, encoding="utf-8")
    (tmp_path / "README.md").write_text("# doc\n" * 900, encoding="utf-8")
    result = compute_score(scan_project(tmp_path))
    size_deductions = [
        d
        for d in result.deductions
        if d.rule in ("giant file", "large file")
    ]
    assert [d.reason for d in size_deductions] == ["huge.py (900 lines)"]
