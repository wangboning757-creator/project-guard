"""Project-scoped TRAE IDE UserPromptSubmit Hook integration."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from .codex_integration import (
    GUARD_ARTIFACT_NAMES,
    CodexIntegrationError,
)
from .codex_integration import (
    resolve_git_root as _resolve_codex_git_root,
)

TRAE_HOOK_COMMAND = "project-guard trae-hook"
TRAE_HOOK_PATH = Path(".trae/hooks.json")
TRAE_HOOK_EVENT = "UserPromptSubmit"
TRAE_HOOK_TIMEOUT_SECONDS = 30
HOOK_CONTEXT = """Project Guard prepared this request.

Before editing production files:
- read .project-guard-instructions.md
- read .project-guard-skill.md
- inspect the Engineering Contract and plan
- create .project-guard-task-contract.json before production edits
- follow Smallest Safe Change and Scope Amendment rules"""


class TraeIntegrationError(RuntimeError):
    """Raised when the project-scoped TRAE integration is unsafe to use."""


@dataclass(frozen=True)
class TraeInstallResult:
    root: Path
    hooks_path: Path
    hooks_changed: bool


def resolve_git_root(
    path: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> Path:
    """Reuse the existing Git-root resolution behavior."""
    try:
        return _resolve_codex_git_root(path, runner=runner)
    except CodexIntegrationError as exc:
        raise TraeIntegrationError(str(exc)) from exc


def _merge_hooks(path: Path) -> tuple[dict[str, Any], bool]:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TraeIntegrationError(f"cannot parse {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise TraeIntegrationError(f"{path} must contain a JSON object")
        if data.get("version", 1) != 1:
            raise TraeIntegrationError(f"{path} has unsupported Hook version")
    else:
        data = {"version": 1}

    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        raise TraeIntegrationError(f"{path} has invalid hooks")
    prompt_hooks = hooks.get(TRAE_HOOK_EVENT, [])
    if not isinstance(prompt_hooks, list):
        raise TraeIntegrationError(f"{path} has invalid UserPromptSubmit hooks")
    for group in prompt_hooks:
        if not isinstance(group, dict):
            raise TraeIntegrationError(f"{path} has an invalid Hook group")
        handlers = group.get("hooks", [])
        if not isinstance(handlers, list) or any(
            not isinstance(handler, dict) for handler in handlers
        ):
            raise TraeIntegrationError(f"{path} has an invalid Hook list")
        for handler in handlers:
            if handler.get("command") != TRAE_HOOK_COMMAND:
                continue
            if handler.get("type") != "command":
                raise TraeIntegrationError(
                    f"{path} has a malformed Project Guard Hook"
                )
            return data, False

    hooks = data.setdefault("hooks", hooks)
    prompt_hooks = hooks.setdefault(TRAE_HOOK_EVENT, [])
    prompt_hooks.append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": TRAE_HOOK_COMMAND,
                    "timeout": TRAE_HOOK_TIMEOUT_SECONDS,
                }
            ]
        }
    )
    return data, True


def install_trae_integration(path: Path) -> TraeInstallResult:
    """Install only the target repository's TRAE Hook configuration."""
    root = resolve_git_root(path)
    hooks_path = root / TRAE_HOOK_PATH
    hooks, hooks_changed = _merge_hooks(hooks_path)

    if hooks_changed:
        try:
            hooks_path.parent.mkdir(parents=True, exist_ok=True)
            hooks_path.write_text(
                json.dumps(hooks, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            raise TraeIntegrationError(f"cannot write {hooks_path}: {exc}") from exc
    return TraeInstallResult(root, hooks_path, hooks_changed)


def _prepare_task(root: Path, prompt: str) -> Any:
    # Import lazily to keep the CLI module and this integration module acyclic.
    from .cli import _prepare_task as prepare_task

    return prepare_task(root, prompt)


def _resolve_payload_root(
    payload: dict[str, Any],
    *,
    git_runner: Callable[..., Any],
) -> Path:
    cwd = payload.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not cwd):
        raise TraeIntegrationError("hook payload has invalid cwd")

    workspace_roots = payload.get("workspace_roots", [])
    if not isinstance(workspace_roots, list):
        raise TraeIntegrationError("hook payload has invalid workspace_roots")
    if any(not isinstance(item, str) or not item for item in workspace_roots):
        raise TraeIntegrationError("workspace_roots must contain paths")

    candidates = ([cwd] if isinstance(cwd, str) else []) + workspace_roots
    if not candidates:
        raise TraeIntegrationError(
            "hook payload is missing cwd/workspace_roots"
        )

    roots: list[Path] = []
    failures: list[str] = []
    for candidate in dict.fromkeys(candidates):
        try:
            root = resolve_git_root(Path(candidate), runner=git_runner)
        except TraeIntegrationError as exc:
            failures.append(str(exc))
            continue
        if root not in roots:
            roots.append(root)
        if isinstance(cwd, str):
            break

    if len(roots) > 1:
        raise TraeIntegrationError(
            "ambiguous workspace: candidates resolve to different Git repositories"
        )
    if roots:
        return roots[0]
    detail = failures[0] if failures else "no Git repository found"
    raise TraeIntegrationError(detail)


def _block(stdout: TextIO, reason: str) -> int:
    stdout.write(json.dumps({
        "decision": "block",
        "reason": f"Project Guard could not prepare this request: {reason}",
    }) + "\n")
    stdout.flush()
    return 0


def run_user_prompt_hook(
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    git_runner: Callable[..., Any] = subprocess.run,
    prepare_runner: Callable[[Path, str], Any] | None = None,
) -> int:
    """Handle TRAE's UserPromptSubmit JSON payload."""
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    try:
        try:
            payload = json.loads(input_stream.read())
        except json.JSONDecodeError as exc:
            raise TraeIntegrationError(
                f"hook payload is invalid JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise TraeIntegrationError("hook payload must be a JSON object")
        event = payload.get("hook_event_name")
        if event != TRAE_HOOK_EVENT:
            raise TraeIntegrationError(
                "hook payload is not a UserPromptSubmit event"
            )
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise TraeIntegrationError("hook payload is missing prompt")

        root = _resolve_payload_root(payload, git_runner=git_runner)
        (prepare_runner or _prepare_task)(root, prompt)
        missing = [
            name for name in GUARD_ARTIFACT_NAMES if not (root / name).is_file()
        ]
        if missing:
            raise TraeIntegrationError(
                "prepare did not generate required Guard artifacts: "
                + ", ".join(missing)
            )
    # This is the final boundary: preparation failures must not silently pass.
    except Exception as exc:  # noqa: BLE001
        return _block(output_stream, str(exc) or "prepare failed")

    output_stream.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": TRAE_HOOK_EVENT,
                    "additionalContext": HOOK_CONTEXT,
                }
            }
        )
        + "\n"
    )
    output_stream.flush()
    return 0
