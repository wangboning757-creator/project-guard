"""Project-scoped Codex CLI UserPromptSubmit integration."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

CODEX_HOOK_COMMAND = "project-guard codex-hook"
GUARD_ARTIFACT_NAMES = (
    ".project-guard-plan.json",
    ".project-guard-contract.json",
    ".project-guard-instructions.md",
    ".project-guard-skill.md",
    ".project-guard-agent-prompt.md",
)
HOOK_CONTEXT = """Project Guard prepared this request.

Before modifying production code:
- read `.project-guard-instructions.md`
- follow `.project-guard-skill.md`
- create/update `.project-guard-task-contract.json`

Ask about material ambiguity. Request a Scope Amendment before out-of-contract production changes."""


class CodexIntegrationError(RuntimeError):
    """Raised when the project-scoped Codex integration cannot be used."""


@dataclass(frozen=True)
class CodexInstallResult:
    root: Path
    hooks_path: Path
    hooks_changed: bool


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_text(path: Path, content: str) -> None:
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    except OSError as exc:
        raise CodexIntegrationError(f"cannot write {path}: {exc}") from exc


def resolve_git_root(
    path: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> Path:
    """Resolve the repository root from a starting directory."""
    cwd = path.resolve()
    if not cwd.is_dir():
        raise CodexIntegrationError(f"cwd does not exist or is not a directory: {cwd}")
    try:
        result = runner(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise CodexIntegrationError(
            f"cannot run Git while resolving repository root from {cwd}: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CodexIntegrationError(
            f"cannot resolve a Git repository from {cwd}"
            + (f": {detail}" if detail else "")
        )
    raw_root = (result.stdout or "").strip()
    if not raw_root:
        raise CodexIntegrationError(
            f"Git did not return a repository root for {cwd}"
        )
    root = Path(raw_root).resolve()
    if not root.is_dir():
        raise CodexIntegrationError(f"Git root is not a directory: {root}")
    return root


def _hook_handler() -> dict[str, Any]:
    return {
        "type": "command",
        "command": CODEX_HOOK_COMMAND,
        "commandWindows": CODEX_HOOK_COMMAND,
    }


def _is_project_guard_hook(handler: object) -> bool:
    if not isinstance(handler, dict) or handler.get("type") != "command":
        return False
    return CODEX_HOOK_COMMAND in (
        handler.get("command"),
        handler.get("commandWindows"),
    )


def _merge_hooks(path: Path) -> tuple[dict[str, Any], bool]:
    if path.is_file():
        try:
            data = json.loads(_read_text(path))
        except (OSError, ValueError) as exc:
            raise CodexIntegrationError(f"cannot parse {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise CodexIntegrationError(f"{path} must contain a JSON object")
    else:
        data = {}

    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        raise CodexIntegrationError(f"{path} has invalid hooks")
    prompt_hooks = hooks.get("UserPromptSubmit", [])
    if not isinstance(prompt_hooks, list):
        raise CodexIntegrationError(
            f"{path} has invalid UserPromptSubmit hooks"
        )
    for group in prompt_hooks:
        if not isinstance(group, dict):
            raise CodexIntegrationError(f"{path} has an invalid hook group")
        handlers = group.get("hooks", [])
        if not isinstance(handlers, list):
            raise CodexIntegrationError(f"{path} has an invalid hook list")
        if any(_is_project_guard_hook(handler) for handler in handlers):
            return data, False

    hooks = data.setdefault("hooks", hooks)
    prompt_hooks = hooks.setdefault("UserPromptSubmit", [])
    prompt_hooks.append({"hooks": [_hook_handler()]})
    return data, True


def install_codex_integration(path: Path) -> CodexInstallResult:
    """Install only the target repository's Codex Hook configuration."""
    root = resolve_git_root(path)
    codex_dir = root / ".codex"
    hooks_path = codex_dir / "hooks.json"
    hooks, hooks_changed = _merge_hooks(hooks_path)

    if hooks_changed:
        codex_dir.mkdir(parents=True, exist_ok=True)
        _write_text(hooks_path, json.dumps(hooks, indent=2) + "\n")
    return CodexInstallResult(
        root=root,
        hooks_path=hooks_path,
        hooks_changed=hooks_changed,
    )


def _block(stdout: TextIO, reason: str) -> int:
    payload = {"decision": "block", "reason": f"Project Guard: {reason}"}
    stdout.write(json.dumps(payload) + "\n")
    stdout.flush()
    return 0


def _prepare_task(root: Path, prompt: str) -> dict[str, Path]:
    # Import lazily to keep the CLI module and this integration module acyclic.
    from .cli import _prepare_task as prepare_task

    return prepare_task(root, prompt)


def _verify_artifacts(root: Path) -> None:
    missing = [
        name for name in GUARD_ARTIFACT_NAMES if not (root / name).is_file()
    ]
    if missing:
        raise CodexIntegrationError(
            "prepare did not generate required Guard artifacts: "
            + ", ".join(missing)
        )


def run_user_prompt_hook(
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    git_runner: Callable[..., Any] = subprocess.run,
    prepare_runner: Callable[[Path, str], Any] | None = None,
) -> int:
    """Handle Codex's UserPromptSubmit JSON payload."""
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    try:
        payload = json.loads(input_stream.read())
        if not isinstance(payload, dict):
            raise CodexIntegrationError("hook payload must be a JSON object")
        if payload.get("hook_event_name") != "UserPromptSubmit":
            raise CodexIntegrationError(
                "hook payload is not a UserPromptSubmit event"
            )
        prompt = payload.get("prompt")
        cwd = payload.get("cwd")
        if not isinstance(prompt, str) or not prompt:
            raise CodexIntegrationError("hook payload is missing prompt")
        if not isinstance(cwd, str) or not cwd:
            raise CodexIntegrationError("hook payload is missing cwd")

        root = resolve_git_root(Path(cwd), runner=git_runner)
        (prepare_runner or _prepare_task)(root, prompt)
        _verify_artifacts(root)
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
