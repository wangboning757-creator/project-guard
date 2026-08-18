"""Project-scoped Cline CLI UserPromptSubmit Hook integration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

CLINE_HOOK_COMMAND = "project-guard cline-hook"
CLINE_HOOK_DIR = Path(".cline/hooks")
WINDOWS_HOOK_PATH = CLINE_HOOK_DIR / "UserPromptSubmit.ps1"
POSIX_HOOK_PATH = CLINE_HOOK_DIR / "UserPromptSubmit"
HOOK_MARKER = "# project-guard-cline-hook:v1"
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
- ask the user about material ambiguity
- request a Scope Amendment for out-of-contract production files

Prefer the Smallest Safe Change and reuse existing capability."""

WINDOWS_HOOK_CONTENT = f'''# Project Guard Cline CLI UserPromptSubmit Hook
{HOOK_MARKER}
$ErrorActionPreference = "Stop"
& "{CLINE_HOOK_COMMAND.split()[0]}" "{CLINE_HOOK_COMMAND.split()[1]}"
exit $LASTEXITCODE
'''
POSIX_HOOK_CONTENT = f'''#!/bin/sh
{HOOK_MARKER}
exec {CLINE_HOOK_COMMAND}
'''


class ClineIntegrationError(RuntimeError):
    """Raised when the project-scoped Cline integration is unsafe to use."""


@dataclass(frozen=True)
class ClineInstallResult:
    root: Path
    windows_hook_path: Path
    posix_hook_path: Path
    windows_hook_changed: bool
    posix_hook_changed: bool


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_text(path: Path, content: str) -> None:
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    except OSError as exc:
        raise ClineIntegrationError(f"cannot write {path}: {exc}") from exc


def resolve_git_root(
    path: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> Path:
    """Resolve the Git repository root from a workspace directory."""
    cwd = path.expanduser().resolve()
    if not cwd.is_dir():
        raise ClineIntegrationError(
            f"workspace root does not exist or is not a directory: {cwd}"
        )
    try:
        result = runner(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ClineIntegrationError(
            f"cannot run Git while resolving repository root from {cwd}: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ClineIntegrationError(
            f"cannot resolve a Git repository from {cwd}"
            + (f": {detail}" if detail else "")
        )
    raw_root = (result.stdout or "").strip()
    if not raw_root:
        raise ClineIntegrationError(
            f"Git did not return a repository root for {cwd}"
        )
    root = Path(raw_root).expanduser().resolve()
    if not root.is_dir():
        raise ClineIntegrationError(f"Git root is not a directory: {root}")
    return root


def _resolve_workspace_root(
    workspace_roots: Iterable[object],
    *,
    git_runner: Callable[..., Any],
) -> Path:
    roots = list(workspace_roots)
    if not roots:
        raise ClineIntegrationError("workspaceRoots must not be empty")
    if any(not isinstance(item, str) or not item for item in roots):
        raise ClineIntegrationError("workspaceRoots must contain paths")

    git_roots: set[Path] = set()
    failures: list[str] = []
    for item in roots:
        try:
            git_roots.add(resolve_git_root(Path(item), runner=git_runner))
        except ClineIntegrationError as exc:
            failures.append(str(exc))

    if len(git_roots) > 1:
        raise ClineIntegrationError(
            "ambiguous multi-root workspace: workspaceRoots resolve to "
            "different Git repositories"
        )
    if git_roots:
        return next(iter(git_roots))
    detail = failures[0] if failures else "no Git repository found"
    raise ClineIntegrationError(detail)


def _owned_hook_state(path: Path, expected: str) -> bool:
    """Return whether a file is unchanged, rejecting unknown content."""
    if not path.exists():
        return True
    try:
        current = _read_text(path)
    except OSError as exc:
        raise ClineIntegrationError(f"cannot read {path}: {exc}") from exc
    if current == expected:
        return False
    raise ClineIntegrationError(
        f"cannot safely update existing Cline Hook: {path}"
    )


def _install_hook_file(path: Path, content: str) -> bool:
    changed = _owned_hook_state(path, content)
    if not changed:
        return False
    _write_text(path, content)
    return True


def install_cline_integration(path: Path) -> ClineInstallResult:
    """Install only the target repository's Cline CLI project Hooks."""
    root = resolve_git_root(path, runner=subprocess.run)
    hooks_dir = root / CLINE_HOOK_DIR
    windows_path = root / WINDOWS_HOOK_PATH
    posix_path = root / POSIX_HOOK_PATH

    # Validate both dedicated files before writing either one. This prevents a
    # malformed Project Guard-owned file from causing a partial installation.
    windows_changed = _owned_hook_state(windows_path, WINDOWS_HOOK_CONTENT)
    posix_changed = _owned_hook_state(posix_path, POSIX_HOOK_CONTENT)
    if windows_changed or posix_changed:
        hooks_dir.mkdir(parents=True, exist_ok=True)
    if windows_changed:
        _write_text(windows_path, WINDOWS_HOOK_CONTENT)
    if posix_changed:
        _write_text(posix_path, POSIX_HOOK_CONTENT)
        try:
            os.chmod(posix_path, 0o755)
        except OSError:
            # The file remains usable on platforms where chmod is unavailable.
            pass
    return ClineInstallResult(
        root=root,
        windows_hook_path=windows_path,
        posix_hook_path=posix_path,
        windows_hook_changed=windows_changed,
        posix_hook_changed=posix_changed,
    )


def _prepare_task(root: Path, prompt: str) -> dict[str, Path]:
    # Import lazily to keep the CLI module and this integration module acyclic.
    from .cli import _prepare_task as prepare_task

    return prepare_task(root, prompt)


def _verify_artifacts(root: Path) -> None:
    missing = [
        name for name in GUARD_ARTIFACT_NAMES if not (root / name).is_file()
    ]
    if missing:
        raise ClineIntegrationError(
            "prepare did not generate required Guard artifacts: "
            + ", ".join(missing)
        )


def _write_response(stdout: TextIO, *, cancel: bool, message: str) -> None:
    stdout.write(
        json.dumps(
            {
                "cancel": cancel,
                "contextModification": "" if cancel else HOOK_CONTEXT,
                "errorMessage": message if cancel else "",
            }
        )
        + "\n"
    )
    stdout.flush()


def run_user_prompt_hook(
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    git_runner: Callable[..., Any] = subprocess.run,
    prepare_runner: Callable[[Path, str], Any] | None = None,
) -> int:
    """Handle Cline's file-hook UserPromptSubmit JSON payload."""
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    try:
        try:
            payload = json.loads(input_stream.read())
        except json.JSONDecodeError as exc:
            raise ClineIntegrationError(
                f"hook payload is invalid JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ClineIntegrationError("hook payload must be a JSON object")
        if payload.get("hookName") != "UserPromptSubmit":
            raise ClineIntegrationError(
                "hook payload is not a UserPromptSubmit event"
            )
        task_id = payload.get("taskId")
        if not isinstance(task_id, str) or not task_id:
            raise ClineIntegrationError("hook payload is missing taskId")
        prompt_event = payload.get("userPromptSubmit")
        if not isinstance(prompt_event, dict):
            raise ClineIntegrationError(
                "hook payload is missing userPromptSubmit"
            )
        prompt = prompt_event.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise ClineIntegrationError("hook payload is missing prompt")
        workspace_roots = payload.get("workspaceRoots")
        if not isinstance(workspace_roots, list):
            raise ClineIntegrationError(
                "hook payload is missing workspaceRoots"
            )
        root = _resolve_workspace_root(workspace_roots, git_runner=git_runner)
        (prepare_runner or _prepare_task)(root, prompt)
        _verify_artifacts(root)
    # This is the final boundary: a malformed or failed preparation must not
    # silently turn a governed prompt into an ungoverned one.  Cline's file
    # Hook protocol reports this result through cancel/errorMessage.
    except Exception as exc:  # noqa: BLE001
        _write_response(
            output_stream,
            cancel=True,
            message=f"Project Guard preparation failed: {exc}",
        )
        return 0

    _write_response(output_stream, cancel=False, message="")
    return 0
