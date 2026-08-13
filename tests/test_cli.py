from typer.testing import CliRunner

from project_guard.cli import app

runner = CliRunner()


def test_inspect_command(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    result = runner.invoke(app, ["inspect", str(tmp_path)])
    assert result.exit_code == 0
    assert "Total lines: 1" in result.output
    assert "Python: 1" in result.output


def test_plan_command(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    result = runner.invoke(
        app, ["plan", str(tmp_path), "Add PDF export"]
    )
    assert result.exit_code == 0
    assert "Potential duplication: no" in result.output


def test_plan_output_plan_writes_snapshot(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    out = tmp_path / "plan.json"
    result = runner.invoke(
        app,
        [
            "plan",
            str(tmp_path),
            "Add PDF export",
            "--output-plan",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert out.is_file()
    assert '"goal": "Add PDF export"' in out.read_text(encoding="utf-8")
    assert "Plan snapshot written" in result.output


def test_plan_output_instructions_writes_file(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    out = tmp_path / "instructions.md"
    result = runner.invoke(
        app,
        [
            "plan",
            str(tmp_path),
            "Add PDF export",
            "--output-instructions",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert "# Project Guard Agent Instructions" in content
    assert "Add PDF export." in content
    assert "Agent instructions written" in result.output


def test_plan_without_output_flags_creates_no_files(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    result = runner.invoke(app, ["plan", str(tmp_path), "Add PDF export"])
    assert result.exit_code == 0
    assert not (tmp_path / ".project-guard-plan.json").exists()
    assert not (tmp_path / ".project-guard-instructions.md").exists()
    assert not (tmp_path / "instructions.md").exists()


def test_plan_output_plan_and_instructions_together(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    plan_out = tmp_path / "plan.json"
    inst_out = tmp_path / "instructions.md"
    result = runner.invoke(
        app,
        [
            "plan",
            str(tmp_path),
            "Add PDF export",
            "--output-plan",
            str(plan_out),
            "--output-instructions",
            str(inst_out),
        ],
    )
    assert result.exit_code == 0
    assert plan_out.is_file()
    assert inst_out.is_file()
    assert "Plan snapshot written" in result.output
    assert "Agent instructions written" in result.output


def test_review_missing_plan_errors(tmp_path):
    result = runner.invoke(
        app,
        [
            "review",
            str(tmp_path),
            "--plan",
            str(tmp_path / "missing.json"),
        ],
    )
    assert result.exit_code == 1
    assert "Error" in result.output
