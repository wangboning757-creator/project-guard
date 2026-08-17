import io
import json
import subprocess
from types import SimpleNamespace

from typer.testing import CliRunner

from project_guard.cli import app
from project_guard.codex_integration import run_user_prompt_hook

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
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": str(cwd),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        }
    )


def _handlers(hooks):
    return [
        handler
        for group in hooks["hooks"]["UserPromptSubmit"]
        for handler in group["hooks"]
    ]


def test_init_codex_fresh_installation(tmp_path):
    repo = _repo(tmp_path)

    result = runner.invoke(app, ["init-codex", str(repo)])

    assert result.exit_code == 0
    hooks_path = repo / ".codex" / "hooks.json"
    assert hooks_path.is_file()
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    handlers = _handlers(hooks)
    assert len(handlers) == 1
    assert handlers[0]["type"] == "command"
    assert handlers[0]["command"] == "project-guard codex-hook"
    assert handlers[0]["commandWindows"] == "project-guard codex-hook"
    assert "Project Guard Codex CLI integration installed." in result.output
    assert "trust the project Hook" in result.output


def test_init_codex_preserves_existing_config_and_hooks(tmp_path):
    repo = _repo(tmp_path)
    hooks_path = repo / ".codex" / "hooks.json"
    hooks_path.parent.mkdir()
    existing = {
        "description": "Existing project hooks",
        "hooks": {
            "UserPromptSubmit": [
                {
                    "matcher": "ignored-by-codex-for-this-event",
                    "hooks": [
                        {"type": "command", "command": "echo existing"}
                    ],
                }
            ],
            "PostToolUse": [
                {"hooks": [{"type": "command", "command": "echo post"}]}
            ],
        },
        "other": "value",
    }
    hooks_path.write_text(json.dumps(existing), encoding="utf-8")

    result = runner.invoke(app, ["init-codex", str(repo)])

    assert result.exit_code == 0
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert hooks["description"] == existing["description"]
    assert hooks["other"] == existing["other"]
    assert hooks["hooks"]["PostToolUse"] == existing["hooks"]["PostToolUse"]
    handlers = _handlers(hooks)
    assert any(handler.get("command") == "echo existing" for handler in handlers)
    assert sum(
        handler.get("command") == "project-guard codex-hook"
        for handler in handlers
    ) == 1


def test_init_codex_is_idempotent(tmp_path):
    repo = _repo(tmp_path)

    first = runner.invoke(app, ["init-codex", str(repo)])
    first_content = (repo / ".codex" / "hooks.json").read_text(
        encoding="utf-8"
    )
    second = runner.invoke(app, ["init-codex", str(repo)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert (
        (repo / ".codex" / "hooks.json").read_text(encoding="utf-8")
        == first_content
    )
    hooks = json.loads(first_content)
    assert sum(
        handler.get("command") == "project-guard codex-hook"
        for handler in _handlers(hooks)
    ) == 1
    assert "already present" in second.output


def test_init_codex_malformed_hooks_json_fails_without_overwriting(tmp_path):
    repo = _repo(tmp_path)
    hooks_path = repo / ".codex" / "hooks.json"
    hooks_path.parent.mkdir()
    original = "{not valid json"
    hooks_path.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-codex", str(repo)])

    assert result.exit_code == 1
    assert "cannot parse" in result.output
    assert hooks_path.read_text(encoding="utf-8") == original


def test_user_prompt_hook_preserves_prompt_and_resolves_git_root(tmp_path):
    repo = _repo(tmp_path)
    subdirectory = repo / "src" / "nested"
    subdirectory.mkdir(parents=True)
    prompt = "Add --exact-value with the text: a & b."
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
    assert not (subdirectory / ".project-guard-contract.json").exists()
    assert not (repo / ".project-guard-task-contract.json").exists()
    response = json.loads(output.getvalue())
    context = response["hookSpecificOutput"]["additionalContext"]
    assert response["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert ".project-guard-instructions.md" in context
    assert ".project-guard-skill.md" in context
    assert ".project-guard-task-contract.json" in context
    assert len(context) < 500


def test_user_prompt_hook_invalid_json_blocks(tmp_path):
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO("{not valid json"),
        stdout=output,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "Expecting" in response["reason"]


def test_user_prompt_hook_missing_prompt_blocks(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload(repo))
    del payload["prompt"]
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=output,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "missing prompt" in response["reason"]


def test_user_prompt_hook_missing_cwd_blocks(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload(repo))
    del payload["cwd"]
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=output,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "missing cwd" in response["reason"]


def test_user_prompt_hook_non_git_cwd_blocks(tmp_path):
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(tmp_path)),
        stdout=output,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "cannot resolve a Git repository" in response["reason"]


def test_user_prompt_hook_git_failure_blocks(tmp_path):
    repo = _repo(tmp_path)
    output = io.StringIO()

    def failed_git(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="git failed")

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(repo)),
        stdout=output,
        git_runner=failed_git,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "git failed" in response["reason"]


def test_user_prompt_hook_prepare_failure_blocks(tmp_path):
    repo = _repo(tmp_path)
    output = io.StringIO()

    def failed_prepare(root, prompt):
        raise RuntimeError("simulated prepare failure")

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(repo)),
        stdout=output,
        prepare_runner=failed_prepare,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "simulated prepare failure" in response["reason"]


def test_user_prompt_hook_rejects_wrong_event(tmp_path):
    repo = _repo(tmp_path)
    payload = json.loads(_payload(repo))
    payload["hook_event_name"] = "PreToolUse"
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=output,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "not a UserPromptSubmit event" in response["reason"]
