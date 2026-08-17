import io
import json
import subprocess

from typer.testing import CliRunner

from project_guard.claude_integration import run_user_prompt_hook
from project_guard.cli import app

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
    return repo


def _payload(cwd, prompt="Add the exact requested feature."):
    return json.dumps(
        {
            "session_id": "session-1",
            "prompt_id": "prompt-1",
            "transcript_path": str(cwd / "transcript.jsonl"),
            "cwd": str(cwd),
            "permission_mode": "default",
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        }
    )


def _handlers(settings):
    return [
        handler
        for group in settings["hooks"]["UserPromptSubmit"]
        for handler in group["hooks"]
    ]


def test_init_claude_fresh_installation(tmp_path):
    repo = _repo(tmp_path)

    result = runner.invoke(app, ["init-claude", str(repo)])

    assert result.exit_code == 0
    assert (repo / ".claude" / "settings.json").is_file()
    assert (repo / ".claude" / "CLAUDE.md").is_file()
    settings = json.loads(
        (repo / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    handlers = _handlers(settings)
    assert len(handlers) == 1
    assert handlers[0]["type"] == "command"
    assert handlers[0]["command"] == "project-guard"
    assert handlers[0]["args"] == ["claude-hook"]
    assert handlers[0]["timeout"] == 30
    assert "Project Guard Claude integration installed." in result.output


def test_init_claude_preserves_existing_settings_and_hooks(tmp_path):
    repo = _repo(tmp_path)
    claude = repo / ".claude"
    claude.mkdir()
    existing = {
        "permissions": {"allow": ["Bash(python *)"]},
        "hooks": {
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo existing",
                        }
                    ],
                }
            ]
        },
        "other": "value",
    }
    settings_path = claude / "settings.json"
    settings_path.write_text(json.dumps(existing), encoding="utf-8")

    result = runner.invoke(app, ["init-claude", str(repo)])

    assert result.exit_code == 0
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["permissions"] == existing["permissions"]
    assert settings["other"] == "value"
    handlers = _handlers(settings)
    assert any(h["command"] == "echo existing" for h in handlers)
    assert sum(h.get("args") == ["claude-hook"] for h in handlers) == 1


def test_init_claude_is_idempotent(tmp_path):
    repo = _repo(tmp_path)

    first = runner.invoke(app, ["init-claude", str(repo)])
    first_settings = (repo / ".claude" / "settings.json").read_text(
        encoding="utf-8"
    )
    first_claude = (repo / ".claude" / "CLAUDE.md").read_text(
        encoding="utf-8"
    )
    second = runner.invoke(app, ["init-claude", str(repo)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert (
        (repo / ".claude" / "settings.json").read_text(encoding="utf-8")
        == first_settings
    )
    assert (
        (repo / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        == first_claude
    )
    assert first_claude.count("<!-- project-guard:start -->") == 1
    assert first_claude.count("<!-- project-guard:end -->") == 1
    assert "already present" in second.output


def test_init_claude_preserves_existing_claude_md_content(tmp_path):
    repo = _repo(tmp_path)
    claude = repo / ".claude"
    claude.mkdir()
    before = "# Existing instructions\n\nKeep this content unchanged.\n"
    path = claude / "CLAUDE.md"
    path.write_text(before, encoding="utf-8")

    result = runner.invoke(app, ["init-claude", str(repo)])

    assert result.exit_code == 0
    content = path.read_text(encoding="utf-8")
    assert content.startswith(before)
    assert content.count("<!-- project-guard:start -->") == 1
    assert content.count("<!-- project-guard:end -->") == 1


def test_user_prompt_hook_preserves_prompt_and_resolves_git_root(tmp_path):
    repo = _repo(tmp_path)
    subdirectory = repo / "src" / "nested"
    subdirectory.mkdir(parents=True)
    prompt = "Add a CLI option named --exact-value with the text: a & b."
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


def test_user_prompt_hook_prepare_failure_blocks(tmp_path):
    repo = _repo(tmp_path)
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(repo)),
        stdout=output,
        prepare_runner=lambda root, prompt: (_ for _ in ()).throw(
            RuntimeError("simulated prepare failure")
        ),
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "simulated prepare failure" in response["reason"]


def test_user_prompt_hook_invalid_non_git_cwd_blocks(tmp_path):
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(_payload(tmp_path)),
        stdout=output,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "cannot resolve a Git repository" in response["reason"]


def test_user_prompt_hook_malformed_payload_blocks(tmp_path):
    repo = _repo(tmp_path)
    output = io.StringIO()

    result = run_user_prompt_hook(
        stdin=io.StringIO(
            json.dumps(
                {
                    "cwd": str(repo),
                    "hook_event_name": "UserPromptSubmit",
                }
            )
        ),
        stdout=output,
    )

    assert result == 0
    response = json.loads(output.getvalue())
    assert response["decision"] == "block"
    assert "missing prompt" in response["reason"]
