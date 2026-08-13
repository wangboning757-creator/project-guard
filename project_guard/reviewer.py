"""Analyze the current git diff for risk signals."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import ValidationError

from .config import (
    DEPENDENCY_FILES,
    DIFF_HUGE_ADDITIONS,
    DIFF_LARGE_ADDITIONS,
    DIFF_LARGE_FILE_ADDED,
    DIFF_MANY_MODULES,
    LARGE_FILE_LINES,
)
from .models import PlanCompliance, PlanSnapshot, ReviewResult
from .planner import (
    MIN_EVIDENCE_TOKEN_MATCHES,
    _goal_evidence_tokens,
    _has_abstraction_expansion_intent,
    _has_direct_capability_evidence,
    _identifier_tokens,
    _keywords,
    _token_overlap,
)
from .python_index import ModuleIndex, index_python_file, index_python_source
from .scanner import count_lines, iter_files


class NotAGitRepoError(RuntimeError):
    pass


class PlanSnapshotError(RuntimeError):
    pass


RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def merge_risk(first: str, second: str) -> str:
    return max((first, second), key=lambda r: RISK_ORDER.get(r, 0))


def load_plan_snapshot(path: Path) -> PlanSnapshot:
    if not path.is_file():
        raise PlanSnapshotError(f"plan file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanSnapshotError(
            f"cannot parse plan file {path}: {exc}"
        ) from exc
    if data.get("version") != 1:
        raise PlanSnapshotError(
            f"unsupported plan snapshot version: {data.get('version')!r} "
            "(expected 1)"
        )
    try:
        return PlanSnapshot.model_validate(data)
    except ValidationError as exc:
        raise PlanSnapshotError(
            f"invalid plan snapshot: {exc.errors()}"
        ) from exc


def _is_test_path(rel: str) -> bool:
    parts = Path(rel).parts
    return (
        "tests" in parts
        or Path(rel).name.startswith("test_")
        or Path(rel).name.endswith("_test.py")
    )


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


def _git_optional(root: Path, *args: str) -> str | None:
    try:
        return _git(root, *args)
    except NotAGitRepoError:
        return None


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


def analyze_diff(
    root: Path, exclude_paths: set[Path] | None = None
) -> ReviewResult:
    root = root.resolve()
    excluded_abs = (
        {p.resolve() for p in exclude_paths} if exclude_paths else set()
    )

    def _is_excluded(rel: str) -> bool:
        if not excluded_abs:
            return False
        try:
            return (root / rel).resolve() in excluded_abs
        except OSError:
            return False

    statuses = [
        (s, p) for s, p in _porcelain(root) if not _is_excluded(p)
    ]
    numstat = {
        p: v for p, v in _numstat(root).items() if not _is_excluded(p)
    }

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
        changed_paths=[p for p in paths if p != ".gitignore"],
        dependency_changed=dependency_changed,
        many_modules_changed=many_modules,
        large_file_additions=large_file_additions,
        changed_python_files=changed_python,
        duplicated_modules=duplicated,
        oversized_changed_files=oversized,
        risk=risk,
        reasons=reasons,
    )


def format_review(
    result: ReviewResult, risk: str | None = None
) -> str:
    lines = [
        f"Git diff review: {result.changed_files} file(s) changed "
        f"(+{result.total_added}/-{result.total_deleted})",
        f"Added files: {result.added_files}",
        f"Deleted files: {result.deleted_files}",
        f"Dependency files changed: {'yes' if result.dependency_changed else 'no'}",
        f"Changed Python modules: {len(result.changed_python_files)}",
        f"Risk level: {risk or result.risk}",
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


def check_plan_compliance(
    snapshot: PlanSnapshot, result: ReviewResult
) -> PlanCompliance:
    allowed = set(snapshot.recommended_scope) | set(snapshot.possible_scope)
    avoid = set(snapshot.avoid_modifying)
    production = [
        p
        for p in result.changed_paths
        if p.endswith(".py") and not _is_test_path(p)
    ]

    violations: list[str] = []
    status = "PASS"
    risk = "LOW"

    avoid_hits = [p for p in production if p in avoid]
    for p in avoid_hits:
        violations.append(f"Modified explicitly avoided file: {p}")
        status = "VIOLATION"
        risk = "HIGH"

    unplanned = [p for p in production if p not in allowed and p not in avoid_hits]
    for p in unplanned:
        violations.append(f"Unplanned production file: {p}")
    if len(unplanned) >= 2:
        status = "VIOLATION"
        risk = "HIGH"
    elif unplanned and status != "VIOLATION":
        status = "WARNING"
        risk = "MEDIUM"

    if snapshot.new_dependency == "not justified" and result.dependency_changed:
        violations.append(
            "Dependency file changed although new dependency was not "
            "justified. Manual verification recommended."
        )
        if status != "VIOLATION":
            status = "WARNING"
        if risk != "HIGH":
            risk = "MEDIUM"

    if snapshot.refactor == "not justified" and len(production) >= 5:
        violations.append(
            f"Possible unplanned refactor: plan marked refactor as not "
            f"justified, but actual change spans {len(production)} production "
            "files."
        )
        status = "VIOLATION"
        risk = "HIGH"

    return PlanCompliance(
        status=status,
        goal=snapshot.goal,
        allowed_scope=sorted(allowed),
        actual_changes=production,
        violations=violations,
        risk=risk,
    )


def _new_top_level_symbols(
    root: Path, result: ReviewResult
) -> dict[str, list[str]]:
    """Top-level classes/functions added by the working-tree diff."""
    added: dict[str, list[str]] = {}
    for rel in result.changed_paths:
        if not rel.endswith(".py") or _is_test_path(rel):
            continue
        full = root / rel
        if not full.is_file():
            continue
        after = index_python_file(full, rel)
        if after is None:
            continue
        before_src = _git_optional(root, "show", f"HEAD:{rel}")
        before = (
            index_python_source(before_src, rel)
            if before_src is not None
            else None
        )
        before_names = (
            set(before.classes) | set(before.top_functions)
            if before is not None
            else set()
        )
        after_names = set(after.classes) | set(after.top_functions)
        new_names = after_names - before_names
        if new_names:
            added[rel] = sorted(new_names)
    return added


def check_reuse_warnings(
    root: Path,
    snapshot: PlanSnapshot,
    result: ReviewResult,
) -> list[str]:
    """High-confidence reuse-before-build warnings (signal only, never a
    violation)."""
    cap_files = snapshot.existing_capability_files
    if not cap_files:
        return []
    if _has_abstraction_expansion_intent(
        snapshot.goal, _keywords(snapshot.goal)
    ):
        return []
    goal_tokens = _goal_evidence_tokens(snapshot.goal)
    if not goal_tokens:
        return []
    changed = set(result.changed_paths)
    if any(cap in changed for cap in cap_files):
        return []

    index: dict[str, ModuleIndex] = {}
    for cap in cap_files:
        idx = index_python_file(root / cap, cap)
        if idx is not None:
            index[cap] = idx
    verified = [
        cap
        for cap in cap_files
        if _has_direct_capability_evidence(cap, goal_tokens, index)
    ]
    if not verified:
        return []

    warnings: list[str] = []
    for rel, new_names in _new_top_level_symbols(root, result).items():
        for name in new_names:
            if (
                _token_overlap(_identifier_tokens(name), goal_tokens)
                >= MIN_EVIDENCE_TOKEN_MATCHES
            ):
                warnings.append(
                    f"possible duplicate implementation: new `{name}` in "
                    f"{rel} overlaps existing capability in {verified[0]}"
                )
    return warnings


def format_plan_compliance(compliance: PlanCompliance) -> str:
    lines = [
        "Plan Compliance:",
        f"Status: {compliance.status}",
        "",
        "Goal:",
        compliance.goal,
        "",
        "Allowed production scope:",
    ]
    lines += [f"- {p}" for p in compliance.allowed_scope] or ["- none"]
    lines += ["", "Actual production changes:"]
    lines += [f"- {p}" for p in compliance.actual_changes] or ["- none"]
    if compliance.violations:
        lines += ["", "Violations:"]
        lines += [f"- {v}" for v in compliance.violations]
    if compliance.reuse_warnings:
        lines += ["", "Possible duplicate implementation:"]
        lines += [f"- {w}" for w in compliance.reuse_warnings]
    return "\n".join(lines)
