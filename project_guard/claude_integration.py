"""Project-scoped Claude Code UserPromptSubmit integration."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

HOOK_COMMAND = "project-guard"
HOOK_ARGS = ["claude-hook"]
HOOK_TIMEOUT_SECONDS = 30
CLAUDE_SECTION_START = "<!-- project-guard:start -->"
CLAUDE_SECTION_END = "<!-- project-guard:end -->"

CLAUDE_BOOTSTRAP = f"""{CLAUDE_SECTION_START}
## Project Guard governed coding workflow

This repository uses project-scoped Project Guard activation for Claude Code. A UserPromptSubmit hook may prepare Guard artifacts before Claude processes each prompt.

For governed coding requests:
- Read `.project-guard-instructions.md` and follow `.project-guard-skill.md`.
- Before production edits, create or update `.project-guard-task-contract.json`.
- Ask the user if materially different interpretations would change behavior.
- Request a Scope Amendment before modifying out-of-contract production files.
- Project Guard provides repository facts and boundaries; Claude remains responsible for semantic interpretation and implementation.
{CLAUDE_SECTION_END}"""

HOOK_CONTEXT = """Project Guard prepared this coding request.

Before modifying production code:
- read `.project-guard-instructions.md`
- follow `.project-guard-skill.md`
- create/update `.project-guard-task-contract.json`

If materially ambiguous, ask the user. If out-of-contract production scope is required, request a Scope Amendment."""


class ClaudeIntegrationError(RuntimeError):
    """Raised when project-scoped Claude integration cannot be installed."""


@dataclass(frozen=True)
class ClaudeInstallResult:
    root: Path
    settings_path: Path
    claude_md_path: Path
    settings_changed: bool
    claude_md_changed: bool


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def resolve_git_root(
    path: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> Path:
    """Resolve the repository root from a starting directory."""
    cwd = path.resolve()
    try:
        result = runner(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ClaudeIntegrationError(
            f"cannot run Git while resolving repository root from {cwd}: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ClaudeIntegrationError(
            f"cannot resolve a Git repository from {cwd}"
            + (f": {detail}" if detail else "")
        )
    raw_root = (result.stdout or "").strip()
    if not raw_root:
        raise ClaudeIntegrationError(
            f"Git did not return a repository root for {cwd}"
        )
    root = Path(raw_root).resolve()
    if not root.is_dir():
        raise ClaudeIntegrationError(f"Git root is not a directory: {root}")
    return root


def _hook_handler() -> dict[str, Any]:
    return {
        "type": "command",
        "command": HOOK_COMMAND,
        "args": HOOK_ARGS.copy(),
        "timeout": HOOK_TIMEOUT_SECONDS,
    }


def _has_project_guard_hook(settings: dict[str, Any]) -> bool:
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        raise ClaudeIntegrationError(".claude/settings.json has invalid hooks")
    prompt_hooks = hooks.get("UserPromptSubmit", [])
    if not isinstance(prompt_hooks, list):
        raise ClaudeIntegrationError(
            ".claude/settings.json has invalid UserPromptSubmit hooks"
        )
    for group in prompt_hooks:
        if not isinstance(group, dict):
            raise ClaudeIntegrationError(
                ".claude/settings.json has an invalid hook group"
            )
        handlers = group.get("hooks", [])
        if not isinstance(handlers, list):
            raise ClaudeIntegrationError(
                ".claude/settings.json has an invalid hook handler list"
            )
        for handler in handlers:
            if not isinstance(handler, dict):
                continue
            if (
                handler.get("type") == "command"
                and handler.get("command") == HOOK_COMMAND
                and handler.get("args") == HOOK_ARGS
            ):
                return True
    return False


def _merge_settings(path: Path) -> tuple[dict[str, Any], bool]:
    if path.is_file():
        try:
            data = json.loads(_read_text(path))
        except (OSError, ValueError) as exc:
            raise ClaudeIntegrationError(
                f"cannot parse {path}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ClaudeIntegrationError(f"{path} must contain a JSON object")
    else:
        data = {}

    if _has_project_guard_hook(data):
        return data, False

    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ClaudeIntegrationError(".claude/settings.json has invalid hooks")
    prompt_hooks = hooks.setdefault("UserPromptSubmit", [])
    if not isinstance(prompt_hooks, list):
        raise ClaudeIntegrationError(
            ".claude/settings.json has invalid UserPromptSubmit hooks"
        )
    prompt_hooks.append({"hooks": [_hook_handler()]})
    return data, True


def _merge_claude_md(path: Path) -> tuple[str, bool]:
    existing = _read_text(path) if path.is_file() else ""
    starts = existing.count(CLAUDE_SECTION_START)
    ends = existing.count(CLAUDE_SECTION_END)
    if starts != ends or starts > 1:
        raise ClaudeIntegrationError(
            f"{path} has an incomplete or duplicated Project Guard section"
        )

    if starts == 1:
        pattern = re.compile(
            re.escape(CLAUDE_SECTION_START)
            + r".*?"
            + re.escape(CLAUDE_SECTION_END),
            re.DOTALL,
        )
        updated = pattern.sub(CLAUDE_BOOTSTRAP, existing, count=1)
    else:
        separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
        updated = existing + separator + CLAUDE_BOOTSTRAP + "\n"
    return updated, updated != existing


def install_claude_integration(path: Path) -> ClaudeInstallResult:
    """Install or update only the target repository's Claude configuration."""
    root = resolve_git_root(path)
    claude_dir = root / ".claude"
    settings_path = claude_dir / "settings.json"
    claude_md_path = claude_dir / "CLAUDE.md"

    settings, settings_changed = _merge_settings(settings_path)
    claude_md, claude_md_changed = _merge_claude_md(claude_md_path)

    claude_dir.mkdir(parents=True, exist_ok=True)
    if settings_changed:
        _write_text(settings_path, json.dumps(settings, indent=2) + "\n")
    if claude_md_changed:
        _write_text(claude_md_path, claude_md)
    return ClaudeInstallResult(
        root=root,
        settings_path=settings_path,
        claude_md_path=claude_md_path,
        settings_changed=settings_changed,
        claude_md_changed=claude_md_changed,
    )


def _block(stdout: TextIO, reason: str) -> int:
    payload = {"decision": "block", "reason": f"Project Guard: {reason}"}
    stdout.write(json.dumps(payload) + "\n")
    stdout.flush()
    return 0


def _prepare_task(root: Path, prompt: str) -> None:
    # Import lazily to keep the CLI module and this integration module acyclic.
    from .cli import _prepare_task as prepare_task

    prepare_task(root, prompt)


def run_user_prompt_hook(
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    git_runner: Callable[..., Any] = subprocess.run,
    prepare_runner: Callable[[Path, str], Any] | None = None,
) -> int:
    """Handle Claude Code's UserPromptSubmit JSON payload."""
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    try:
        payload = json.loads(input_stream.read())
        if not isinstance(payload, dict):
            raise ClaudeIntegrationError("hook payload must be a JSON object")
        if payload.get("hook_event_name") != "UserPromptSubmit":
            raise ClaudeIntegrationError(
                "hook payload is not a UserPromptSubmit event"
            )
        prompt = payload.get("prompt")
        cwd = payload.get("cwd")
        if not isinstance(prompt, str) or not prompt:
            raise ClaudeIntegrationError("hook payload is missing prompt")
        if not isinstance(cwd, str) or not cwd:
            raise ClaudeIntegrationError("hook payload is missing cwd")

        root = resolve_git_root(Path(cwd), runner=git_runner)
        (prepare_runner or _prepare_task)(root, prompt)
    # This is the final safety boundary: ordinary internal failures must block.
    except Exception as exc:  # noqa: BLE001
        return _block(output_stream, str(exc) or "prepare failed")

    output_stream.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": HOOK_CONTEXT,
                }
            }
        )
        + "\n"
    )
    output_stream.flush()
    return 0
