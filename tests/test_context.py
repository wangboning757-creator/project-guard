from project_guard.context import build_context
from project_guard.scanner import scan_project


def test_context_includes_entry_points_and_rules(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\nKeep files small.\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nproject-guard = "project_guard.cli:app"\n',
        encoding="utf-8",
    )
    md = build_context(tmp_path, scan_project(tmp_path))
    assert "## Entry Points" in md
    assert "`main.py`" in md
    assert "console script `project-guard`" in md
    assert "Keep files small." in md
    assert "## Main Modules" in md
    assert "## Dependencies" in md
