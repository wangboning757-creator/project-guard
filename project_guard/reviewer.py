"""Analyze the current git diff for risk signals."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import (
    DEPENDENCY_FILES,
    DIFF_HUGE_ADDITIONS,
    DIFF_LARGE_ADDITIONS,
    DIFF_LARGE_FILE_ADDED,
    DIFF_MANY_MODULES,
    LARGE_FILE_LINES,
)
from .models import ReviewResult
from .scanner import count_lines, iter_files


class NotAGitRepoError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable not found") from exc
    if proc.returncode != 0:
        raise NotAGitRepoError((proc.stderr or proc.stdout or "").strip())
    return proc.stdout


def _porcelain(root: Path) -> list[tuple[str, str]]:
    out = _git(root, "status", "--porcelain", "--untracked-files=all")
    items: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line:
            continue
        xy, _, path = line[:2], line[2:3], line[3:]
        if xy == "??":
            items.append(("A", path))
        elif xy[0] == "R":
            items.append(("R", path.split(" -> ")[-1]))
        elif xy[0] in ("A", "D", "M"):
            items.append((xy[0], path))
    return items


def _numstat(root: Path) -> dict[str, tuple[int, int]]:
    stats: dict[str, tuple[int, int]] = {}
    for args in (["diff", "--numstat"], ["diff", "--cached", "--numstat"]):
        for line in _git(root, *args).splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            added, deleted = parts[0], parts[1]
            path = parts[2].split(" => ")[-1]
            a = int(added) if added.isdigit() else 0
            d = int(deleted) if deleted.isdigit() else 0
            pa, pd = stats.get(path, (0, 0))
            stats[path] = (pa + a, pd + d)
    return stats


def _existing_stem_map(root: Path) -> dict[str, list[str]]:
    stem_map: dict[str, list[str]] = {}
    for path in iter_files(root):
        if path.suffix != ".py":
            continue
        stem = path.stem.lower()
        if stem in ("__init__", "__main__"):
            continue
        stem_map.setdefault(stem, []).append(
            path.relative_to(root).as_posix()
        )
    return stem_map


def analyze_diff(root: Path) -> ReviewResult:
    root = root.resolve()
    statuses = _porcelain(root)
    numstat = _numstat(root)

    changed: dict[str, str] = {}
    added_files = 0
    deleted_files = 0
    for status, path in statuses:
        changed[path] = status
        if status == "A":
            added_files += 1
        elif status == "D":
            deleted_files += 1

    paths = sorted(set(changed) | set(numstat))
    total_added = 0
    total_deleted = 0
    large_file_additions: list[str] = []
    changed_python: list[str] = []
    oversized: list[str] = []
    for path in paths:
        added, deleted = numstat.get(path, (0, 0))
        if changed.get(path) == "A" and added == 0 and deleted == 0:
            full = root / path
            added = count_lines(full) if full.is_file() else 0
        total_added += added
        total_deleted += deleted
        if added >= DIFF_LARGE_FILE_ADDED:
            large_file_additions.append(f"{path} (+{added})")
        if path.endswith(".py"):
            changed_python.append(path)
            full = root / path
            if full.is_file() and count_lines(full) >= LARGE_FILE_LINES:
                oversized.append(path)

    dependency_changed = any(Path(p).name in DEPENDENCY_FILES for p in paths)
    many_modules = len(changed_python) > DIFF_MANY_MODULES

    stem_map = _existing_stem_map(root)
    duplicated: list[str] = []
    for path in paths:
        if changed.get(path) != "A" or not path.endswith(".py"):
            continue
        stem = Path(path).stem.lower()
        if stem in ("__init__", "__main__"):
            continue
        others = [p for p in stem_map.get(stem, []) if p != path]
        if others:
            duplicated.append(f"{path} (also: {', '.join(others)})")

    reasons: list[str] = []
    if dependency_changed:
        reasons.append("dependency files changed")
    if total_added >= DIFF_HUGE_ADDITIONS:
        reasons.append(f"very large diff (+{total_added} lines)")
    elif total_added >= DIFF_LARGE_ADDITIONS:
        reasons.append(f"large diff (+{total_added} lines)")
    if large_file_additions:
        reasons.append(
            "large single-file additions: " + ", ".join(large_file_additions)
        )
    if many_modules:
        reasons.append(f"{len(changed_python)} Python modules changed")
    if duplicated:
        reasons.append(
            "possible duplicated modules: " + ", ".join(duplicated)
        )
    if oversized:
        reasons.append("oversized changed files: " + ", ".join(oversized))

    if total_added >= DIFF_HUGE_ADDITIONS or (
        dependency_changed and many_modules
    ):
        risk = "HIGH"
    elif (
        total_added >= DIFF_LARGE_ADDITIONS
        or many_modules
        or dependency_changed
        or large_file_additions
        or duplicated
        or oversized
    ):
        risk = "MEDIUM"
    else:
        risk = "LOW"

    if not reasons:
        reasons.append("no significant risk signals")

    return ReviewResult(
        changed_files=len(paths),
        added_files=added_files,
        deleted_files=deleted_files,
        total_added=total_added,
        total_deleted=total_deleted,
        dependency_changed=dependency_changed,
        many_modules_changed=many_modules,
        large_file_additions=large_file_additions,
        changed_python_files=changed_python,
        duplicated_modules=duplicated,
        oversized_changed_files=oversized,
        risk=risk,
        reasons=reasons,
    )


def format_review(result: ReviewResult) -> str:
    lines = [
        f"Git diff review: {result.changed_files} file(s) changed "
        f"(+{result.total_added}/-{result.total_deleted})",
        f"Added files: {result.added_files}",
        f"Deleted files: {result.deleted_files}",
        f"Dependency files changed: {'yes' if result.dependency_changed else 'no'}",
        f"Changed Python modules: {len(result.changed_python_files)}",
        f"Risk level: {result.risk}",
        "",
        "Reasons:",
    ]
    lines.extend(f"  - {r}" for r in result.reasons)
    for label, items in (
        ("Large file additions:", result.large_file_additions),
        ("Suspected duplicated modules:", result.duplicated_modules),
        ("Oversized changed files:", result.oversized_changed_files),
    ):
        if items:
            lines.append(label)
            lines.extend(f"  - {i}" for i in items)
    return "\n".join(lines)
