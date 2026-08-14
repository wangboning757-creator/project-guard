import json
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


def test_prepare_happy_path(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    result = runner.invoke(app, ["prepare", str(tmp_path), "Add PDF export"])
    assert result.exit_code == 0
    for name in (
        ".project-guard-plan.json",
        ".project-guard-contract.json",
        ".project-guard-instructions.md",
        ".project-guard-skill.md",
        ".project-guard-agent-prompt.md",
    ):
        assert (tmp_path / name).is_file()
    assert not (tmp_path / ".project-guard-task-contract.json").exists()
    assert "Project Guard task prepared." in result.output
    assert "Agent handoff:" in result.output
    assert ".project-guard-agent-prompt.md" in result.output


def test_prepare_artifacts_match_plan_explicit_outputs(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    goal = "Add PDF export"
    plan_json = tmp_path / "p.json"
    contract_json = tmp_path / "c.json"
    inst = tmp_path / "i.md"
    plan_result = runner.invoke(
        app,
        [
            "plan",
            str(tmp_path),
            goal,
            "--output-plan",
            str(plan_json),
            "--output-contract",
            str(contract_json),
            "--output-instructions",
            str(inst),
        ],
    )
    assert plan_result.exit_code == 0

    prepare_result = runner.invoke(
        app, ["prepare", str(tmp_path), goal]
    )
    assert prepare_result.exit_code == 0
    assert (
        (tmp_path / ".project-guard-plan.json").read_text(
            encoding="utf-8"
        )
        == plan_json.read_text(encoding="utf-8")
    )
    assert (
        (tmp_path / ".project-guard-contract.json").read_text(
            encoding="utf-8"
        )
        == contract_json.read_text(encoding="utf-8")
    )
    assert (
        (tmp_path / ".project-guard-instructions.md").read_text(
            encoding="utf-8"
        )
        == inst.read_text(encoding="utf-8")
    )
    from project_guard.instructions import skill_template_text

    assert (
        (tmp_path / ".project-guard-skill.md").read_text(
            encoding="utf-8"
        )
        == skill_template_text()
    )


def test_prepare_does_not_touch_task_contract(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    task = tmp_path / ".project-guard-task-contract.json"
    original = '{"version": 1, "original_request": "old"}'
    task.write_text(original, encoding="utf-8")
    result = runner.invoke(app, ["prepare", str(tmp_path), "Add PDF export"])
    assert result.exit_code == 0
    assert task.read_text(encoding="utf-8") == original
    assert "agent-owned and was left unchanged" in result.output


def _init_git_repo_with_main(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "main.py").write_text(
        "print('export pdf')\n", encoding="utf-8"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def _fake_claude_success(cwd):
    (cwd / "main.py").write_text(
        "print('export pdf')\nprint(2)\n", encoding="utf-8"
    )
    (cwd / ".project-guard-task-contract.json").write_text(
        json.dumps(
            {
                "version": 1,
                "original_request": "Add PDF export",
                "scope_amendments": [],
            }
        ),
        encoding="utf-8",
    )


def _mock_claude_resolution(monkeypatch, executable="claude.exe"):
    monkeypatch.setattr(
        "project_guard.cli._resolve_claude_executable",
        lambda: executable,
    )


def test_run_prepares_before_invoking_claude(tmp_path, monkeypatch):
    repo = _init_git_repo_with_main(tmp_path)
    calls = []
    _mock_claude_resolution(monkeypatch)

    def fake_run(cmd, cwd):
        calls.append((cmd, cwd))
        for name in (
            ".project-guard-plan.json",
            ".project-guard-contract.json",
            ".project-guard-instructions.md",
            ".project-guard-skill.md",
            ".project-guard-agent-prompt.md",
        ):
            assert (cwd / name).is_file()
        _fake_claude_success(cwd)
        return 0

    monkeypatch.setattr("project_guard.cli._run_claude", fake_run)
    result = runner.invoke(app, ["run", str(repo), "Add PDF export"])
    assert result.exit_code == 0
    assert calls
    assert calls[0][0][0] == "claude.exe"
    assert "Project Guard: preparing task" in result.output
    assert "Project Guard: reviewing changes" in result.output


def test_run_agent_prompt_handoff(tmp_path, monkeypatch):
    repo = _init_git_repo_with_main(tmp_path)
    captured = {}
    _mock_claude_resolution(monkeypatch)

    def fake_run(cmd, cwd):
        captured["cmd"] = cmd
        _fake_claude_success(cwd)
        return 0

    monkeypatch.setattr("project_guard.cli._run_claude", fake_run)
    result = runner.invoke(app, ["run", str(repo), "Add PDF export"])
    assert result.exit_code == 0
    assert captured["cmd"][0] == "claude.exe"
    prompt = (repo / ".project-guard-agent-prompt.md").read_text(
        encoding="utf-8"
    )
    assert captured["cmd"][1] == prompt
    assert "Do not commit" in prompt
    assert "--print" not in captured["cmd"]


def test_claude_command_contract():
    from project_guard.cli import _claude_command

    assert _claude_command("C:\\npm\\claude.CMD", "hello") == [
        "C:\\npm\\claude.CMD",
        "hello",
    ]


def test_resolve_claude_executable_uses_which(monkeypatch):
    import project_guard.cli as cli_mod

    monkeypatch.setattr(
        cli_mod.shutil,
        "which",
        lambda name: "C:\\fake\\claude.CMD"
        if name == "claude"
        else None,
    )
    assert cli_mod._resolve_claude_executable() == "C:\\fake\\claude.CMD"


def test_run_missing_claude_executable(tmp_path, monkeypatch):
    repo = _init_git_repo_with_main(tmp_path)
    monkeypatch.setattr(
        "project_guard.cli._resolve_claude_executable", lambda: None
    )
    launched = []

    def fake_run(cmd, cwd):
        launched.append(cmd)
        return 0

    monkeypatch.setattr("project_guard.cli._run_claude", fake_run)
    result = runner.invoke(app, ["run", str(repo), "Add PDF export"])
    assert result.exit_code == 1
    assert "Claude Code executable was not found." in result.output
    assert launched == []
    assert "Plan Compliance" not in result.output
    assert "Traceback" not in result.output


def test_run_uses_resolved_windows_cmd_shim(tmp_path, monkeypatch):
    repo = _init_git_repo_with_main(tmp_path)
    captured = {}
    _mock_claude_resolution(
        monkeypatch, "C:\\Users\\wn186\\AppData\\Roaming\\npm\\claude.CMD"
    )

    def fake_run(cmd, cwd):
        captured["cmd"] = cmd
        _fake_claude_success(cwd)
        return 0

    monkeypatch.setattr("project_guard.cli._run_claude", fake_run)
    result = runner.invoke(app, ["run", str(repo), "Add PDF export"])
    assert result.exit_code == 0
    assert (
        captured["cmd"][0]
        == "C:\\Users\\wn186\\AppData\\Roaming\\npm\\claude.CMD"
    )
    assert "--print" not in captured["cmd"]


def test_run_claude_nonzero_exit(tmp_path, monkeypatch):
    repo = _init_git_repo_with_main(tmp_path)
    _mock_claude_resolution(monkeypatch)

    def fail_run(cmd, cwd):
        return 2

    monkeypatch.setattr("project_guard.cli._run_claude", fail_run)
    result = runner.invoke(app, ["run", str(repo), "Add PDF export"])
    assert result.exit_code == 2
    assert "Claude Code exited with status 2" in result.output
    assert "Project Guard run was not completed" in result.output
    assert "Plan Compliance" not in result.output


def test_run_missing_task_contract(tmp_path, monkeypatch):
    repo = _init_git_repo_with_main(tmp_path)
    _mock_claude_resolution(monkeypatch)

    def success_no_task(cmd, cwd):
        return 0

    monkeypatch.setattr("project_guard.cli._run_claude", success_no_task)
    result = runner.invoke(app, ["run", str(repo), "Add PDF export"])
    assert result.exit_code == 1
    assert "without producing" in result.output
    assert ".project-guard-task-contract.json." in result.output
    assert "Project Guard review was not run." in result.output
    assert "Plan Compliance" not in result.output


def test_run_stale_task_contract(tmp_path, monkeypatch):
    repo = _init_git_repo_with_main(tmp_path)
    _mock_claude_resolution(monkeypatch)
    (repo / ".project-guard-task-contract.json").write_text(
        json.dumps(
            {
                "version": 1,
                "original_request": "old goal",
                "scope_amendments": [],
            }
        ),
        encoding="utf-8",
    )

    def success(cmd, cwd):
        return 0

    monkeypatch.setattr("project_guard.cli._run_claude", success)
    result = runner.invoke(app, ["run", str(repo), "Add PDF export"])
    assert result.exit_code == 1
    assert "did not update the Agent-owned Task Contract" in result.output
    assert "Project Guard review was not run." in result.output
    assert "Plan Compliance" not in result.output


def test_run_successful_orchestration(tmp_path, monkeypatch):
    repo = _init_git_repo_with_main(tmp_path)
    _mock_claude_resolution(monkeypatch)

    def fake_run(cmd, cwd):
        _fake_claude_success(cwd)
        return 0

    monkeypatch.setattr("project_guard.cli._run_claude", fake_run)
    result = runner.invoke(app, ["run", str(repo), "Add PDF export"])
    assert result.exit_code == 0
    assert "Plan Compliance:" in result.output
    assert "Status: PASS" in result.output
    assert "Risk level: LOW" in result.output


def test_run_claude_inherits_stdio(monkeypatch):
    from pathlib import Path

    import project_guard.cli as cli_mod

    captured = {}

    class FakeProc:
        returncode = 0

    def fake_subprocess_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(cli_mod.subprocess, "run", fake_subprocess_run)
    rc = cli_mod._run_claude(["claude.exe", "prompt"], Path("."))
    assert rc == 0
    assert "capture_output" not in captured["kwargs"]
    assert "stdin" not in captured["kwargs"]
    assert "stdout" not in captured["kwargs"]
    assert "stderr" not in captured["kwargs"]
    assert "--print" not in captured["cmd"]
