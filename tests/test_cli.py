import subprocess

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
    assert "# Original User Request" in content
    assert "Add PDF export" in content
    assert "# Mandatory Coding Skill" in content
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


def test_plan_output_contract_writes_file(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    out = tmp_path / "contract.json"
    result = runner.invoke(
        app,
        [
            "plan",
            str(tmp_path),
            "Add PDF export",
            "--output-contract",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert '"original_request": "Add PDF export"' in content
    assert '"explicit_requirements"' in content
    assert "Engineering contract written" in result.output


def test_plan_output_skill_writes_template(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    out = tmp_path / "skill.md"
    result = runner.invoke(
        app,
        [
            "plan",
            str(tmp_path),
            "Add PDF export",
            "--output-skill",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert "Requirement Fidelity" in content
    assert "Smallest Safe Change" in content
    assert "Coding skill written" in result.output


def test_plan_contract_skill_instructions_together(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    contract_out = tmp_path / "contract.json"
    skill_out = tmp_path / "skill.md"
    inst_out = tmp_path / "instructions.md"
    result = runner.invoke(
        app,
        [
            "plan",
            str(tmp_path),
            "Add PDF export",
            "--output-contract",
            str(contract_out),
            "--output-skill",
            str(skill_out),
            "--output-instructions",
            str(inst_out),
        ],
    )
    assert result.exit_code == 0
    assert contract_out.is_file()
    assert skill_out.is_file()
    assert inst_out.is_file()
    inst = inst_out.read_text(encoding="utf-8")
    assert "skill.md" in inst
    assert "Add PDF export" in inst


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


def _git(root, *args):
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_review_excludes_plan_and_instructions(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")
    (tmp_path / "app.py").write_text(
        "print(1)\nprint(2)\n", encoding="utf-8"
    )
    (tmp_path / ".project-guard-plan.json").write_text(
        '{"version": 1, "goal": "x", "recommended_scope": ["app.py"], '
        '"possible_scope": [], "avoid_modifying": [], '
        '"new_dependency": "not justified", '
        '"new_abstraction": "not justified", "refactor": "not justified"}',
        encoding="utf-8",
    )
    (tmp_path / ".project-guard-instructions.md").write_text(
        "# instructions\n", encoding="utf-8"
    )
    result = runner.invoke(
        app,
        [
            "review",
            str(tmp_path),
            "--plan",
            str(tmp_path / ".project-guard-plan.json"),
            "--instructions",
            str(tmp_path / ".project-guard-instructions.md"),
        ],
    )
    assert result.exit_code == 0
    assert "Git diff review: 1 file(s) changed" in result.output
    assert "Plan Compliance:" in result.output
    assert "Status: PASS" in result.output


def test_review_missing_instructions_errors(tmp_path):
    result = runner.invoke(
        app,
        [
            "review",
            str(tmp_path),
            "--instructions",
            str(tmp_path / "missing.md"),
        ],
    )
    assert result.exit_code == 1
    assert "file not found" in result.output


def test_review_with_contract(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")
    (tmp_path / "app.py").write_text(
        "print(1)\nprint(2)\n", encoding="utf-8"
    )
    (tmp_path / "contract.json").write_text(
        '{"version": 1, "original_request": "Add a CLI option", '
        '"explicit_requirements": ["Add a CLI option"], '
        '"inferred_requirements": [], "assumptions": [], '
        '"unresolved_questions": [], "repository_facts": [], '
        '"recommended_scope": ["app.py"], "possible_scope": [], '
        '"avoid_modifying": [], "existing_capability_files": [], '
        '"new_dependency": "not justified", '
        '"new_abstraction": "not justified", "refactor": "not justified", '
        '"complexity_budget": {}, "testing_policy": ""}',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "review",
            str(tmp_path),
            "--contract",
            str(tmp_path / "contract.json"),
        ],
    )
    assert result.exit_code == 0
    assert "Plan Compliance:" in result.output
    assert "Status: PASS" in result.output
    assert "Requirement Fidelity:" in result.output
    assert "Complexity Signal:" in result.output
    assert "Remediation Constraints:" in result.output


def _init_repo_with_early_stop_diff(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")
    (tmp_path / "app.py").write_text(
        "print(1)\nprint(2)\n", encoding="utf-8"
    )
    (tmp_path / "workflow.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "contract.json").write_text(
        '{"version": 1, "original_request": "Add early-stop option", '
        '"explicit_requirements": ["Add early-stop option"], '
        '"inferred_requirements": [], "assumptions": [], '
        '"unresolved_questions": [], "repository_facts": [], '
        '"recommended_scope": ["app.py"], "possible_scope": [], '
        '"avoid_modifying": [], "existing_capability_files": [], '
        '"new_dependency": "not justified", '
        '"new_abstraction": "not justified", "refactor": "not justified", '
        '"complexity_budget": {}, "testing_policy": ""}',
        encoding="utf-8",
    )
    return tmp_path


def test_review_with_task_contract_approved(tmp_path):
    repo = _init_repo_with_early_stop_diff(tmp_path)
    (repo / "task.json").write_text(
        '{"version": 1, "original_request": "Add early-stop option", '
        '"scope_amendments": [{"requested_files": ["workflow.py"], '
        '"reason": "workflow owns stop decision", '
        '"safe_in_scope_alternative_exists": false, '
        '"status": "approved"}]}',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "review",
            str(repo),
            "--contract",
            str(repo / "contract.json"),
            "--task-contract",
            str(repo / "task.json"),
        ],
    )
    assert result.exit_code == 0
    assert "Status: PASS" in result.output
    assert "Approved scope amendments:" in result.output
    assert "- workflow.py" in result.output
    assert "Unplanned production file: workflow.py" not in result.output


def test_review_task_contract_mismatch(tmp_path):
    repo = _init_repo_with_early_stop_diff(tmp_path)
    (repo / "task.json").write_text(
        '{"version": 1, "original_request": "Add max-sources option", '
        '"scope_amendments": []}',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "review",
            str(repo),
            "--contract",
            str(repo / "contract.json"),
            "--task-contract",
            str(repo / "task.json"),
        ],
    )
    assert result.exit_code == 1
    assert "Task Contract mismatch" in result.output
    assert "original_request does not match Guard Contract" in result.output


def test_review_task_contract_requires_contract(tmp_path):
    result = runner.invoke(
        app,
        [
            "review",
            str(tmp_path),
            "--task-contract",
            str(tmp_path / "task.json"),
        ],
    )
    assert result.exit_code == 1
    assert "--task-contract requires --contract" in result.output


def test_review_task_contract_missing(tmp_path):
    repo = _init_repo_with_early_stop_diff(tmp_path)
    result = runner.invoke(
        app,
        [
            "review",
            str(repo),
            "--contract",
            str(repo / "contract.json"),
            "--task-contract",
            str(repo / "missing.json"),
        ],
    )
    assert result.exit_code == 1
    assert "task contract file not found" in result.output


def test_review_task_contract_malformed(tmp_path):
    repo = _init_repo_with_early_stop_diff(tmp_path)
    (repo / "task.json").write_text("{not json", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "review",
            str(repo),
            "--contract",
            str(repo / "contract.json"),
            "--task-contract",
            str(repo / "task.json"),
        ],
    )
    assert result.exit_code == 1
    assert "cannot parse task contract" in result.output


def test_review_task_contract_unsupported_version(tmp_path):
    repo = _init_repo_with_early_stop_diff(tmp_path)
    (repo / "task.json").write_text('{"version": 2}', encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "review",
            str(repo),
            "--contract",
            str(repo / "contract.json"),
            "--task-contract",
            str(repo / "task.json"),
        ],
    )
    assert result.exit_code == 1
    assert "unsupported task contract version" in result.output
