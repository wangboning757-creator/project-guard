import io
import json
import subprocess
from types import SimpleNamespace

from typer.testing import CliRunner

from project_guard.cli import app
from project_guard.copilot_integration import run_user_prompt_hook

runner = CliRunner()


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "main.py").write_text("print(1)\n", encoding="utf-8")
    return repo


def _payload(cwd, prompt="Add the exact requested feature."):
    return json.dumps(
        {
            "sessionId": "session-1",
            "timestamp": 1704614400000,
            "cwd": str(cwd),
            "prompt": prompt,
        }
    )


def _hook_entries(config):
    return config["hooks"]["userPromptSubmitted"]


def test_init_copilot_fresh_installation_uses_official_schema(tmp_path):
    repo = _repo(tmp_path)

    result = runner.invoke(app, ["init-copilot", str(repo)])

    assert result.exit_code == 0
    hooks_path = repo / ".github" / "hooks" / "project-guard.json"
    config = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert config["version"] == 1
    assert len(_hook_entries(config)) == 1
    assert _hook_entries(config)[0] == {
        "type": "command",
        "bash": "project-guard copilot-hook",
        "powershell": "project-guard copilot-hook",
        "timeoutSec": 30,
    }
    assert "GitHub Copilot integration installed." in result.output


def test_init_copilot_is_idempotent(tmp_path):
    repo = _repo(tmp_path)

    first = runner.invoke(app, ["init-copilot", str(repo)])
    path = repo / ".github" / "hooks" / "project-guard.json"
    first_content = path.read_text(encoding="utf-8")
    second = runner.invoke(app, ["init-copilot", str(repo)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert path.read_text(encoding="utf-8") == first_content
    assert "already present" in second.output


def test_init_copilot_does_not_modify_unrelated_hook_file(tmp_path):
    repo = _repo(tmp_path)
    other = repo / ".github" / "hooks" / "other.json"
    other.parent.mkdir(parents=True)
    original = '{"version": 1, "hooks": {"sessionStart": []}}\n'
    other.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-copilot", str(repo)])

    assert result.exit_code == 0
    assert other.read_text(encoding="utf-8") == original


def test_init_copilot_malformed_owned_file_fails_without_overwriting(tmp_path):
    repo = _repo(tmp_path)
    hooks_path = repo / ".github" / "hooks" / "project-guard.json"
    hooks_path.parent.mkdir(parents=True)
    original = "{not valid json"
    hooks_path.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-copilot", str(repo)])

    assert result.exit_code == 1
    assert "cannot parse" in result.output
    assert hooks_path.read_text(encoding="utf-8") == original


def test_init_copilot_unknown_owned_file_fails_without_overwriting(tmp_path):
    repo = _repo(tmp_path)
    hooks_path = repo / ".github" / "hooks" / "project-guard.json"
    hooks_path.parent.mkdir(parents=True)
    original = '{"version": 1, "hooks": {"sessionStart": []}}\n'
    hooks_path.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-copilot", str(repo)])

    assert result.exit_code == 1
    assert "cannot safely update unknown Copilot hook configuration" in result.output
    assert hooks_path.read_text(encoding="utf-8") == original


def test_user_prompt_hook_preserves_prompt_and_resolves_git_root(tmp_path):
    repo = _repo(tmp_path)
    subdirectory = repo / "src" / "nested"
    subdirectory.mkdir(parents=True)
    prompt = "  Add --exact-value with the text: a & b.  "
    output = io.StringIO()
    error = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(subdirectory, prompt)),
        stdout=output,
        stderr=error,
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
    progress = json.loads(output.getvalue())
    assert progress["type"] == "progress"
    assert ".project-guard-instructions.md" in progress["message"]
    assert ".project-guard-skill.md" in progress["message"]
    assert ".project-guard-task-contract.json" in progress["message"]
    assert not error.getvalue()


def test_user_prompt_hook_invalid_json_fails_open_without_fake_block(tmp_path):
    output = io.StringIO()
    error = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO("{not valid json"),
        stdout=output,
        stderr=error,
    )

    assert result == 1
    assert output.getvalue() == ""
    assert "hook payload" in error.getvalue()


def test_user_prompt_hook_missing_prompt_fails(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload(repo))
    del payload["prompt"]
    error = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(json.dumps(payload)),
        stderr=error,
    )

    assert result == 1
    assert "missing prompt" in error.getvalue()


def test_user_prompt_hook_missing_cwd_fails(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload(repo))
    del payload["cwd"]
    error = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(json.dumps(payload)),
        stderr=error,
    )

    assert result == 1
    assert "missing cwd" in error.getvalue()


def test_user_prompt_hook_non_git_cwd_fails(tmp_path):
    error = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(tmp_path)),
        stderr=error,
    )

    assert result == 1
    assert "cannot resolve a Git repository" in error.getvalue()


def test_user_prompt_hook_git_failure_fails(tmp_path):
    repo = _repo(tmp_path)
    error = io.StringIO()

    def failed_git(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="git failed")

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(repo)),
        stderr=error,
        git_runner=failed_git,
    )

    assert result == 1
    assert "git failed" in error.getvalue()


def test_user_prompt_hook_prepare_failure_fails(tmp_path):
    repo = _repo(tmp_path)
    error = io.StringIO()

    def failed_prepare(root, prompt):
        raise RuntimeError("simulated prepare failure")

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(repo)),
        stderr=error,
        prepare_runner=failed_prepare,
    )

    assert result == 1
    assert "simulated prepare failure" in error.getvalue()
