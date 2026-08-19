"""Paths generated and owned by Project Guard itself."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

PROJECT_GUARD_PREPARE_ARTIFACTS = frozenset(
    {
        ".project-guard-plan.json",
        ".project-guard-contract.json",
        ".project-guard-instructions.md",
        ".project-guard-skill.md",
        ".project-guard-agent-prompt.md",
    }
)

PROJECT_GUARD_GOVERNANCE_ARTIFACTS = frozenset(
    {
        ".project-guard-task-contract.json",
        ".project-guard-cline-plugin-loaded",
    }
)

PROJECT_GUARD_INTEGRATION_ARTIFACTS = frozenset(
    {
        ".cline/plugins/project-guard.js",
        ".cline/hooks/UserPromptSubmit.ps1",
        ".cline/hooks/UserPromptSubmit",
    }
)

PROJECT_GUARD_OWNED_PATHS = frozenset(
    PROJECT_GUARD_PREPARE_ARTIFACTS
    | PROJECT_GUARD_GOVERNANCE_ARTIFACTS
    | PROJECT_GUARD_INTEGRATION_ARTIFACTS
)


def normalize_repository_path(rel_path: str | Path) -> str:
    """Return a repository-relative path in stable POSIX form."""
    value = str(rel_path).replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return PurePosixPath(value).as_posix()


def is_project_guard_artifact(rel_path: str | Path) -> bool:
    """Return whether *rel_path* is an exact Project Guard-owned path."""
    return normalize_repository_path(rel_path) in PROJECT_GUARD_OWNED_PATHS
