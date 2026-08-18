import io
import json
import subprocess
from types import SimpleNamespace

from typer.testing import CliRunner

from project_guard.cli import app
from project_guard.trae_integration import run_user_prompt_hook

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


def _payload(cwd, prompt="Add the exact requested feature."):
    return json.dumps(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-1",
            "cwd": str(cwd),
            "workspace_roots": [str(cwd)],
            "prompt": prompt,
        }
    )


def _prompt_hooks(config):
    return config["hooks"]["UserPromptSubmit"]


def _handlers(config):
    return [
        handler
        for group in _prompt_hooks(config)
        for handler in group["hooks"]
    ]


def test_init_trae_fresh_installation_uses_project_hook_schema(tmp_path):
    repo = _repo(tmp_path)

    result = runner.invoke(app, ["init-trae", str(repo)])

    assert result.exit_code == 0
    hooks_path = repo / ".trae" / "hooks.json"
    config = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert config["version"] == 1
    assert _handlers(config) == [
        {
            "type": "command",
            "command": "project-guard trae-hook",
            "timeout": 30,
        }
    ]
    assert "Experimental TRAE IDE integration installed." in result.output
    assert "Settings > Hooks > Project" in result.output


def test_init_trae_preserves_existing_hooks_and_fields(tmp_path):
    repo = _repo(tmp_path)
    hooks_path = repo / ".trae" / "hooks.json"
    hooks_path.parent.mkdir()
    existing = {
        "version": 1,
        "description": "Existing TRAE hooks",
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "echo start"}]}
            ],
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "echo existing"}]}
            ],
        },
        "other": "value",
    }
    hooks_path.write_text(json.dumps(existing), encoding="utf-8")

    result = runner.invoke(app, ["init-trae", str(repo)])

    assert result.exit_code == 0
    config = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert config["description"] == existing["description"]
    assert config["other"] == existing["other"]
    assert config["hooks"]["SessionStart"] == existing["hooks"]["SessionStart"]
    assert any(handler["command"] == "echo existing" for handler in _handlers(config))
    assert sum(
        handler.get("command") == "project-guard trae-hook"
        for handler in _handlers(config)
    ) == 1


def test_init_trae_is_idempotent(tmp_path):
    repo = _repo(tmp_path)

    first = runner.invoke(app, ["init-trae", str(repo)])
    hooks_path = repo / ".trae" / "hooks.json"
    first_content = hooks_path.read_text(encoding="utf-8")
    second = runner.invoke(app, ["init-trae", str(repo)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert hooks_path.read_text(encoding="utf-8") == first_content
    assert "already present" in second.output


def test_init_trae_malformed_hooks_json_fails_without_overwriting(tmp_path):
    repo = _repo(tmp_path)
    hooks_path = repo / ".trae" / "hooks.json"
    hooks_path.parent.mkdir()
    original = "{not valid json"
    hooks_path.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-trae", str(repo)])

    assert result.exit_code == 1
    assert "cannot parse" in result.output
    assert hooks_path.read_text(encoding="utf-8") == original


def test_init_trae_unknown_existing_guard_entry_fails_safely(tmp_path):
    repo = _repo(tmp_path)
    hooks_path = repo / ".trae" / "hooks.json"
    hooks_path.parent.mkdir()
    original = json.dumps(
        {
            "version": 1,
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "project-guard"}]}
                ]
            },
        }
    )
    hooks_path.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-trae", str(repo)])

    assert result.exit_code == 0
    config = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert sum(
        handler.get("command") == "project-guard trae-hook"
        for handler in _handlers(config)
    ) == 1
    assert any(handler.get("command") == "project-guard" for handler in _handlers(config))


def test_init_trae_malformed_project_guard_entry_fails_without_overwriting(tmp_path):
    repo = _repo(tmp_path)
    hooks_path = repo / ".trae" / "hooks.json"
    hooks_path.parent.mkdir()
    original = {
        "version": 1,
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "shell",
                            "command": "project-guard trae-hook",
                        }
                    ]
                }
            ]
        },
    }
    hooks_path.write_text(json.dumps(original), encoding="utf-8")

    result = runner.invoke(app, ["init-trae", str(repo)])

    assert result.exit_code == 1
    assert "malformed Project Guard Hook" in result.output
    assert json.loads(hooks_path.read_text(encoding="utf-8")) == original


def test_trae_hook_preserves_prompt_and_resolves_cwd_git_root(tmp_path):
    repo = _repo(tmp_path)
    subdirectory = repo / "src" / "nested"
    subdirectory.mkdir(parents=True)
    prompt = "  Add --exact-value with the text: a & b.  "
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(subdirectory, prompt)),
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
    response = json.loads(output.getvalue())
    context = response["hookSpecificOutput"]["additionalContext"]
    assert response["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert ".project-guard-instructions.md" in context
    assert ".project-guard-skill.md" in context
    assert ".project-guard-task-contract.json" in context
    assert "Requirement Fidelity" not in context
    assert len(context) < 600


def test_trae_hook_uses_workspace_root_when_cwd_is_missing(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload(repo))
    del payload["cwd"]
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=output,
    )

    assert result == 0
    assert (repo / ".project-guard-contract.json").is_file()


def test_trae_hook_invalid_json_blocks(tmp_path):
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO("{not valid json"),
        stdout=output,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "invalid JSON" in response["reason"]


def test_trae_hook_missing_prompt_blocks(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload(repo))
    del payload["prompt"]
    output = io.StringIO()

    run_user_prompt_hook(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=output,
    )

    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "missing prompt" in response["reason"]


def test_trae_hook_missing_workspace_blocks(tmp_path):
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Add a feature",
    }
    output = io.StringIO()

    run_user_prompt_hook(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=output,
    )

    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "cwd/workspace_roots" in response["reason"]


def test_trae_hook_non_git_workspace_blocks(tmp_path):
    output = io.StringIO()

    def failed_git(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="not a repo")

    run_user_prompt_hook(
        stdin=io.StringIO(_payload(tmp_path)),
        stdout=output,
        git_runner=failed_git,
    )

    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "not a repo" in response["reason"]


def test_trae_hook_git_failure_blocks(tmp_path):
    repo = _repo(tmp_path)
    output = io.StringIO()

    def failed_git(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="git failed")

    run_user_prompt_hook(
        stdin=io.StringIO(_payload(repo)),
        stdout=output,
        git_runner=failed_git,
    )

    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "git failed" in response["reason"]


def test_trae_hook_prepare_failure_blocks(tmp_path):
    repo = _repo(tmp_path)
    output = io.StringIO()

    def failed_prepare(root, prompt):
        raise RuntimeError("simulated prepare failure")

    run_user_prompt_hook(
        stdin=io.StringIO(_payload(repo)),
        stdout=output,
        prepare_runner=failed_prepare,
    )

    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "simulated prepare failure" in response["reason"]


def test_trae_hook_rejects_wrong_event(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload(repo))
    payload["hook_event_name"] = "PreToolUse"
    output = io.StringIO()

    run_user_prompt_hook(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=output,
    )

    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "not a UserPromptSubmit event" in response["reason"]
