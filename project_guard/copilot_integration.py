"""Project-scoped GitHub Copilot repository hook integration."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

COPILOT_HOOK_COMMAND = "project-guard copilot-hook"
HOOK_TIMEOUT_SECONDS = 30
HOOK_PATH = Path(".github/hooks/project-guard.json")
GUARD_ARTIFACT_NAMES = (
    ".project-guard-plan.json",
    ".project-guard-contract.json",
    ".project-guard-instructions.md",
    ".project-guard-skill.md",
    ".project-guard-agent-prompt.md",
)
HOOK_PROGRESS_CONTEXT = (
    "Project Guard prepared this prompt. Read "
    ".project-guard-instructions.md and .project-guard-skill.md; "
    "create/update .project-guard-task-contract.json before production edits. "
    "Ask about material ambiguity, request a Scope Amendment for out-of-contract "
    "production files, and use the Smallest Safe Change with existing capability "
    "reuse."
)


class CopilotIntegrationError(RuntimeError):
    """Raised when the project-scoped Copilot integration is unsafe to use."""


@dataclass(frozen=True)
class CopilotInstallResult:
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
        raise CopilotIntegrationError(f"cannot write {path}: {exc}") from exc


def resolve_git_root(
    path: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> Path:
    """Resolve the repository root from a starting directory."""
    cwd = path.resolve()
    if not cwd.is_dir():
        raise CopilotIntegrationError(
            f"cwd does not exist or is not a directory: {cwd}"
        )
    try:
        result = runner(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise CopilotIntegrationError(
            f"cannot run Git while resolving repository root from {cwd}: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CopilotIntegrationError(
            f"cannot resolve a Git repository from {cwd}"
            + (f": {detail}" if detail else "")
        )
    raw_root = (result.stdout or "").strip()
    if not raw_root:
        raise CopilotIntegrationError(
            f"Git did not return a repository root for {cwd}"
        )
    root = Path(raw_root).resolve()
    if not root.is_dir():
        raise CopilotIntegrationError(f"Git root is not a directory: {root}")
    return root


def _hook_handler() -> dict[str, Any]:
    return {
        "type": "command",
        "bash": COPILOT_HOOK_COMMAND,
        "powershell": COPILOT_HOOK_COMMAND,
        "timeoutSec": HOOK_TIMEOUT_SECONDS,
    }


def _is_project_guard_hook(handler: object) -> bool:
    if not isinstance(handler, dict):
        return False
    return (
        handler.get("type") == "command"
        and handler.get("bash") == COPILOT_HOOK_COMMAND
        and handler.get("powershell") == COPILOT_HOOK_COMMAND
    )


def _merge_hooks(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.is_file():
        return (
            {
                "version": 1,
                "hooks": {"userPromptSubmitted": [_hook_handler()]},
            },
            True,
        )

    try:
        data = json.loads(_read_text(path))
    except (OSError, ValueError) as exc:
        raise CopilotIntegrationError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CopilotIntegrationError(f"{path} must contain a JSON object")
    if data.get("version") != 1 or not isinstance(data.get("hooks"), dict):
        raise CopilotIntegrationError(
            f"cannot safely update unknown Copilot hook configuration: {path}"
        )

    hooks = data["hooks"]
    prompt_hooks = hooks.get("userPromptSubmitted")
    if not isinstance(prompt_hooks, list):
        raise CopilotIntegrationError(
            f"cannot safely update unknown Copilot hook configuration: {path}"
        )
    if any(not isinstance(item, dict) for item in prompt_hooks):
        raise CopilotIntegrationError(f"{path} has invalid userPromptSubmitted hooks")
    if any(_is_project_guard_hook(item) for item in prompt_hooks):
        return data, False
    raise CopilotIntegrationError(
        f"{path} is valid JSON but is not a recognized Project Guard configuration"
    )


def install_copilot_integration(path: Path) -> CopilotInstallResult:
    """Install only the target repository's Copilot repository Hook."""
    root = resolve_git_root(path)
    hooks_path = root / HOOK_PATH
    hooks, hooks_changed = _merge_hooks(hooks_path)
    if hooks_changed:
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(hooks_path, json.dumps(hooks, indent=2) + "\n")
    return CopilotInstallResult(
        root=root,
        hooks_path=hooks_path,
        hooks_changed=hooks_changed,
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
        raise CopilotIntegrationError(
            "prepare did not generate required Guard artifacts: "
            + ", ".join(missing)
        )


def run_user_prompt_hook(
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    git_runner: Callable[..., Any] = subprocess.run,
    prepare_runner: Callable[[Path, str], Any] | None = None,
) -> int:
    """Handle GitHub Copilot's camelCase userPromptSubmitted payload."""
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    try:
        try:
            payload = json.loads(input_stream.read())
        except json.JSONDecodeError as exc:
            raise CopilotIntegrationError(
                f"hook payload is invalid JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise CopilotIntegrationError("hook payload must be a JSON object")
        prompt = payload.get("prompt")
        cwd = payload.get("cwd")
        if not isinstance(prompt, str) or not prompt:
            raise CopilotIntegrationError("hook payload is missing prompt")
        if not isinstance(cwd, str) or not cwd:
            raise CopilotIntegrationError("hook payload is missing cwd")

        root = resolve_git_root(Path(cwd), runner=git_runner)
        (prepare_runner or _prepare_task)(root, prompt)
        _verify_artifacts(root)
    except Exception as exc:  # noqa: BLE001
        # GitHub documents userPromptSubmitted command hooks as fail-open.
        error_stream.write(f"Project Guard Copilot Hook failed: {exc}\n")
        error_stream.flush()
        return 1

    # Command-config userPromptSubmitted output is not injected into the model.
    # This official progress format is display-only and keeps that limitation
    # explicit instead of pretending that additionalContext is supported here.
    output_stream.write(
        json.dumps({"type": "progress", "message": HOOK_PROGRESS_CONTEXT})
        + "\n"
    )
    output_stream.flush()
    return 0
