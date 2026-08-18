import io
import json
import subprocess
from types import SimpleNamespace

from typer.testing import CliRunner

from project_guard.cli import app
from project_guard.cline_integration import run_user_prompt_hook

runner = CliRunner()


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _repo(tmp_path, name="repo"):
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "main.py").write_text("print(1)\n", encoding="utf-8")
    return repo


def _payload(workspace_roots, prompt="  Add the exact feature: a & b.  "):
    return json.dumps(
        {
            "taskId": "task-1",
            "hookName": "UserPromptSubmit",
            "timestamp": "1704614400000",
            "workspaceRoots": [str(path) for path in workspace_roots],
            "userPromptSubmit": {"prompt": prompt},
        }
    )


def _response(output):
    return json.loads(output.getvalue())


def test_init_cline_fresh_installation_uses_cli_project_hook_paths(tmp_path):
    repo = _repo(tmp_path)

    result = runner.invoke(app, ["init-cline", str(repo)])

    assert result.exit_code == 0
    windows = repo / ".cline" / "hooks" / "UserPromptSubmit.ps1"
    posix = repo / ".cline" / "hooks" / "UserPromptSubmit"
    assert windows.is_file()
    assert posix.is_file()
    assert "project-guard-cline-hook:v1" in windows.read_text(encoding="utf-8")
    assert 'project-guard" "cline-hook' in windows.read_text(encoding="utf-8")
    assert posix.read_text(encoding="utf-8").startswith("#!/bin/sh\n")
    assert "exec project-guard cline-hook" in posix.read_text(encoding="utf-8")
    assert not (repo / ".clinerules" / "hooks").exists()
    assert "Cline CLI integration installed." in result.output


def test_init_cline_is_idempotent(tmp_path):
    repo = _repo(tmp_path)

    first = runner.invoke(app, ["init-cline", str(repo)])
    windows = repo / ".cline" / "hooks" / "UserPromptSubmit.ps1"
    posix = repo / ".cline" / "hooks" / "UserPromptSubmit"
    first_contents = (windows.read_text(encoding="utf-8"), posix.read_text(encoding="utf-8"))
    second = runner.invoke(app, ["init-cline", str(repo)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert (windows.read_text(encoding="utf-8"), posix.read_text(encoding="utf-8")) == first_contents
    assert "already present" in second.output


def test_init_cline_preserves_unrelated_hooks(tmp_path):
    repo = _repo(tmp_path)
    other = repo / ".cline" / "hooks" / "OtherHook.ps1"
    other.parent.mkdir(parents=True)
    original = "Write-Output 'user hook'\n"
    other.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-cline", str(repo)])

    assert result.exit_code == 0
    assert other.read_text(encoding="utf-8") == original


def test_init_cline_rejects_unknown_existing_project_guard_hook(tmp_path):
    repo = _repo(tmp_path)
    path = repo / ".cline" / "hooks" / "UserPromptSubmit.ps1"
    path.parent.mkdir(parents=True)
    original = "# user-owned hook\n"
    path.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-cline", str(repo)])

    assert result.exit_code == 1
    assert "cannot safely update existing Cline Hook" in result.output
    assert path.read_text(encoding="utf-8") == original
    assert not (repo / ".cline" / "hooks" / "UserPromptSubmit").exists()


def test_cline_hook_preserves_prompt_and_resolves_subdirectory_git_root(tmp_path):
    repo = _repo(tmp_path)
    subdirectory = repo / "src" / "nested"
    subdirectory.mkdir(parents=True)
    prompt = "  Add --exact-value with the text: a & b.  "
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload([subdirectory], prompt)),
        stdout=output,
    )

    assert result == 0
    contract = json.loads(
        (repo / ".project-guard-contract.json").read_text(encoding="utf-8")
    )
    assert contract["original_request"] == prompt
    for name in (
        ".project-guard-plan.json",
        ".project-guard-contract.json",
        ".project-guard-instructions.md",
        ".project-guard-skill.md",
        ".project-guard-agent-prompt.md",
    ):
        assert (repo / name).is_file()
    assert not (repo / ".project-guard-task-contract.json").exists()
    response = _response(output)
    assert response["cancel"] is False
    assert response["errorMessage"] == ""
    assert ".project-guard-instructions.md" in response["contextModification"]
    assert ".project-guard-skill.md" in response["contextModification"]
    assert ".project-guard-task-contract.json" in response["contextModification"]
    assert "Requirement Fidelity" not in response["contextModification"]
    assert len(response["contextModification"]) < 700


def test_cline_hook_accepts_multiple_workspace_roots_with_same_git_root(tmp_path):
    repo = _repo(tmp_path)
    subdirectory = repo / "src"
    subdirectory.mkdir()
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload([repo, subdirectory])),
        stdout=output,
    )

    assert result == 0
    assert _response(output)["cancel"] is False


def test_cline_hook_rejects_ambiguous_multi_root_workspace(tmp_path):
    first = _repo(tmp_path, "first")
    second = _repo(tmp_path, "second")
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload([first, second])),
        stdout=output,
    )

    response = _response(output)
    assert result == 0
    assert response["cancel"] is True
    assert "ambiguous multi-root workspace" in response["errorMessage"]


def test_cline_hook_rejects_invalid_json(tmp_path):
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO("{not valid json"),
        stdout=output,
    )

    response = _response(output)
    assert result == 0
    assert response["cancel"] is True
    assert "invalid JSON" in response["errorMessage"]


def test_cline_hook_rejects_missing_task_id(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload([repo]))
    del payload["taskId"]
    output = io.StringIO()

    run_user_prompt_hook(stdin=io.StringIO(json.dumps(payload)), stdout=output)

    response = _response(output)
    assert response["cancel"] is True
    assert "missing taskId" in response["errorMessage"]


def test_cline_hook_rejects_missing_prompt(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload([repo]))
    del payload["userPromptSubmit"]["prompt"]
    output = io.StringIO()

    run_user_prompt_hook(stdin=io.StringIO(json.dumps(payload)), stdout=output)

    response = _response(output)
    assert response["cancel"] is True
    assert "missing prompt" in response["errorMessage"]


def test_cline_hook_rejects_missing_or_empty_workspace_roots(tmp_path):
    repo = _repo(tmp_path)
    for workspace_roots in (None, []):
        payload = json.loads(_payload([repo]))
        payload["workspaceRoots"] = workspace_roots
        output = io.StringIO()

        run_user_prompt_hook(
            stdin=io.StringIO(json.dumps(payload)),
            stdout=output,
        )

        response = _response(output)
        assert response["cancel"] is True
        assert "workspaceRoots" in response["errorMessage"]


def test_cline_hook_rejects_non_git_workspace(tmp_path):
    output = io.StringIO()

    run_user_prompt_hook(
        stdin=io.StringIO(_payload([tmp_path])),
        stdout=output,
    )

    response = _response(output)
    assert response["cancel"] is True
    assert "Git repository" in response["errorMessage"]


def test_cline_hook_rejects_wrong_hook_name(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload([repo]))
    payload["hookName"] = "TaskStart"
    output = io.StringIO()

    run_user_prompt_hook(stdin=io.StringIO(json.dumps(payload)), stdout=output)

    response = _response(output)
    assert response["cancel"] is True
    assert "not a UserPromptSubmit event" in response["errorMessage"]


def test_cline_hook_git_failure_blocks(tmp_path):
    repo = _repo(tmp_path)
    output = io.StringIO()

    def failed_git(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="git failed")

    run_user_prompt_hook(
        stdin=io.StringIO(_payload([repo])),
        stdout=output,
        git_runner=failed_git,
    )

    response = _response(output)
    assert response["cancel"] is True
    assert "git failed" in response["errorMessage"]


def test_cline_hook_prepare_failure_blocks(tmp_path):
    repo = _repo(tmp_path)
    output = io.StringIO()

    def failed_prepare(root, prompt):
        raise RuntimeError("simulated prepare failure")

    run_user_prompt_hook(
        stdin=io.StringIO(_payload([repo])),
        stdout=output,
        prepare_runner=failed_prepare,
    )

    response = _response(output)
    assert response["cancel"] is True
    assert "simulated prepare failure" in response["errorMessage"]

