"""Analyze the current git diff for risk signals."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import ValidationError

from .artifacts import is_project_guard_artifact
from .config import (
    DEPENDENCY_FILES,
    DIFF_HUGE_ADDITIONS,
    DIFF_LARGE_ADDITIONS,
    DIFF_LARGE_FILE_ADDED,
    DIFF_MANY_MODULES,
    LARGE_FILE_LINES,
    SOURCE_EXTENSIONS,
)
from .models import (
    ComplexitySignal,
    ContractAmendment,
    EngineeringContract,
    PlanCompliance,
    PlanSnapshot,
    RemediationConstraint,
    ReviewResult,
    TaskContract,
)
from .planner import (
    MIN_EVIDENCE_TOKEN_MATCHES,
    _goal_evidence_tokens,
    _has_abstraction_expansion_intent,
    _has_direct_capability_evidence,
    _identifier_tokens,
    _keywords,
    _token_overlap,
)
from .python_index import ModuleIndex
from .scanner import count_lines, iter_files
from .symbol_index import index_source_file, index_source_text


class NotAGitRepoError(RuntimeError):
    pass


class PlanSnapshotError(RuntimeError):
    pass


class ContractError(RuntimeError):
    pass


class TaskContractError(RuntimeError):
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


def load_engineering_contract(path: Path) -> EngineeringContract:
    if not path.is_file():
        raise ContractError(f"contract file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractError(
            f"cannot parse contract file {path}: {exc}"
        ) from exc
    if data.get("version") != 1:
        raise ContractError(
            f"unsupported contract version: {data.get('version')!r} "
            "(expected 1)"
        )
    try:
        return EngineeringContract.model_validate(data)
    except ValidationError as exc:
        raise ContractError(
            f"invalid engineering contract: {exc.errors()}"
        ) from exc


def contract_to_snapshot(
    contract: EngineeringContract,
) -> PlanSnapshot:
    return PlanSnapshot(
        goal=contract.original_request,
        recommended_scope=contract.recommended_scope,
        possible_scope=contract.possible_scope,
        avoid_modifying=contract.avoid_modifying,
        new_dependency=contract.new_dependency,
        new_abstraction=contract.new_abstraction,
        refactor=contract.refactor,
        existing_capability_files=contract.existing_capability_files,
    )


def load_task_contract(path: Path) -> TaskContract:
    if not path.is_file():
        raise TaskContractError(f"task contract file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TaskContractError(
            f"cannot parse task contract file {path}: {exc}"
        ) from exc
    if data.get("version") != 1:
        raise TaskContractError(
            f"unsupported task contract version: {data.get('version')!r} "
            "(expected 1)"
        )
    try:
        return TaskContract.model_validate(data)
    except ValidationError as exc:
        raise TaskContractError(
            f"invalid task contract: {exc.errors()}"
        ) from exc


def approved_amendment_files(task_contract: TaskContract) -> list[str]:
    """Files approved by the user via status == \"approved\" amendments."""
    files: list[str] = []
    for amendment in task_contract.scope_amendments:
        if amendment.status == "approved":
            files.extend(amendment.requested_files)
    return files


def _is_test_path(rel: str) -> bool:
    parts = Path(rel).parts
    name = Path(rel).name.lower()
    stem = Path(rel).stem.lower()
    return (
        "tests" in parts
        or "__tests__" in parts
        or "test" in parts
        or ("src" in parts and "test" in parts)
        or name.startswith("test_")
        or stem.endswith(("_test", ".test", ".spec"))
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
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
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
        if is_project_guard_artifact(rel):
            return True
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
    changed_source: list[str] = []
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
        if Path(path).suffix.lower() in SOURCE_EXTENSIONS:
            changed_source.append(path)
            if path.endswith(".py"):
                changed_python.append(path)
            full = root / path
            if full.is_file() and count_lines(full) >= LARGE_FILE_LINES:
                oversized.append(path)

    dependency_changed = any(Path(p).name in DEPENDENCY_FILES for p in paths)
    many_modules = len(changed_source) > DIFF_MANY_MODULES

    stem_map = _existing_stem_map(root)
    duplicated: list[str] = []
    for path in paths:
        if (
            changed.get(path) != "A"
            or Path(path).suffix.lower() not in SOURCE_EXTENSIONS
        ):
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
        reasons.append(f"{len(changed_source)} source modules changed")
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
        added_paths=[
            p
            for p in paths
            if p != ".gitignore" and changed.get(p) == "A"
        ],
        dependency_changed=dependency_changed,
        many_modules_changed=many_modules,
        large_file_additions=large_file_additions,
        changed_python_files=changed_python,
        changed_source_files=changed_source,
        duplicated_modules=duplicated,
        oversized_changed_files=oversized,
        risk=risk,
        reasons=reasons,
    )


def format_review(
    result: ReviewResult,
    risk: str | None = None,
    extra_reasons: list[str] | None = None,
) -> str:
    reasons = list(result.reasons)
    if extra_reasons:
        reasons = [
            r for r in reasons if r != "no significant risk signals"
        ]
        reasons.extend(extra_reasons)
    lines = [
        (
            f"Git diff review: {result.changed_files} file(s) changed "
            f"(+{result.total_added}/-{result.total_deleted})"
        ),
        f"Added files: {result.added_files}",
        f"Deleted files: {result.deleted_files}",
        f"Dependency files changed: {'yes' if result.dependency_changed else 'no'}",
        f"Changed source modules: {len(result.changed_source_files)}",
        f"Risk level: {risk or result.risk}",
        "",
        "Reasons:",
    ]
    lines.extend(f"  - {r}" for r in reasons)
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
    snapshot: PlanSnapshot,
    result: ReviewResult,
    amendments: list[ContractAmendment] | None = None,
) -> PlanCompliance:
    allowed = set(snapshot.recommended_scope) | set(snapshot.possible_scope)
    avoid = set(snapshot.avoid_modifying)
    approved_files: list[str] = []
    if amendments:
        for amendment in amendments:
            if amendment.status == "approved":
                approved_files.extend(amendment.requested_files)
    approved_set = set(approved_files)
    effective_allowed = allowed | approved_set
    effective_avoid = avoid - approved_set
    production = [
        p
        for p in result.changed_paths
        if Path(p).suffix.lower() in SOURCE_EXTENSIONS and not _is_test_path(p)
    ]

    violations: list[str] = []
    status = "PASS"
    risk = "LOW"

    avoid_hits = [p for p in production if p in effective_avoid]
    for p in avoid_hits:
        violations.append(f"Modified explicitly avoided file: {p}")
        status = "VIOLATION"
        risk = "HIGH"

    unplanned = [
        p
        for p in production
        if p not in effective_allowed and p not in avoid_hits
    ]
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
        original_allowed_scope=sorted(allowed),
        approved_scope_amendments=sorted(approved_set),
        effective_allowed_scope=sorted(effective_allowed),
        avoid_overridden=sorted(approved_set & avoid),
    )


def _new_top_level_symbols(
    root: Path, result: ReviewResult
) -> dict[str, tuple[list[str], list[str]]]:
    """Top-level classes/functions added by the diff per file."""
    added: dict[str, tuple[list[str], list[str]]] = {}
    for rel in result.changed_paths:
        if (
            Path(rel).suffix.lower() not in SOURCE_EXTENSIONS
            or _is_test_path(rel)
        ):
            continue
        full = root / rel
        if not full.is_file():
            continue
        after = index_source_file(full, rel)
        if after is None:
            continue
        before_src = _git_optional(root, "show", f"HEAD:{rel}")
        before = (
            index_source_text(before_src, rel)
            if before_src is not None
            else None
        )
        before_classes = set(before.classes) if before is not None else set()
        before_functions = (
            set(
                before.top_functions
                if before.language == "python"
                else before.functions
            )
            if before is not None
            else set()
        )
        new_classes = set(after.classes) - before_classes
        after_functions = (
            after.top_functions
            if after.language == "python"
            else after.functions
        )
        new_functions = set(after_functions) - before_functions
        if new_classes or new_functions:
            added[rel] = (
                sorted(new_classes),
                sorted(new_functions),
            )
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
        idx = index_source_file(root / cap, cap)
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
    for rel, (new_classes, new_functions) in _new_top_level_symbols(
        root, result
    ).items():
        for name in new_classes + new_functions:
            if (
                _token_overlap(_identifier_tokens(name), goal_tokens)
                >= MIN_EVIDENCE_TOKEN_MATCHES
            ):
                warnings.append(
                    f"possible duplicate implementation: new `{name}` in "
                    f"{rel} overlaps existing capability in {verified[0]}"
                )
    return warnings


def check_complexity(
    root: Path,
    contract: EngineeringContract,
    result: ReviewResult,
) -> ComplexitySignal:
    """Compare the diff increment against the contract's preferred budget."""
    budget = contract.complexity_budget
    production = [
        p
        for p in result.changed_paths
        if Path(p).suffix.lower() in SOURCE_EXTENSIONS and not _is_test_path(p)
    ]
    new_files = [
        p
        for p in result.added_paths
        if Path(p).suffix.lower() in SOURCE_EXTENSIONS and not _is_test_path(p)
    ]
    new_classes = 0
    new_functions = 0
    for classes, functions in _new_top_level_symbols(root, result).values():
        new_classes += len(classes)
        new_functions += len(functions)

    over_budget = []
    if (
        len(production)
        > budget.preferred_max_touched_production_files + 2
    ):
        over_budget.append("touched production files")
    if (
        new_classes >= 2
        and len(production) <= budget.preferred_max_touched_production_files
    ):
        over_budget.append("multiple new top-level classes")
    if result.dependency_changed and contract.new_dependency == "not justified":
        over_budget.append("new dependency not justified")
    if (
        new_files
        and new_classes
        and len(production) > budget.preferred_max_touched_production_files
    ):
        over_budget.append("new files with abstraction-like structure")

    return ComplexitySignal(
        level="MEDIUM" if over_budget else "LOW",
        touched_production_files=len(production),
        new_production_files=len(new_files),
        new_top_level_classes=new_classes,
        new_top_level_functions=new_functions,
        dependency_changed=result.dependency_changed,
    )


def check_requirement_fidelity(
    contract: EngineeringContract,
    result: ReviewResult,
) -> str:
    """Structural-only fidelity signal.

    Project Guard does not determine semantic correctness; it only checks
    for obvious structural conflicts.
    """
    if not contract.explicit_requirements:
        return "NEEDS HUMAN CONFIRMATION"
    production = [
        p
        for p in result.changed_paths
        if Path(p).suffix.lower() in SOURCE_EXTENSIONS and not _is_test_path(p)
    ]
    allowed = set(contract.recommended_scope) | set(contract.possible_scope)
    if production and not any(p in allowed for p in production):
        return "NEEDS HUMAN CONFIRMATION"
    return "STRUCTURAL CHECK ONLY"


def build_remediation_constraints(
    compliance: PlanCompliance,
    reuse_warnings: list[str],
) -> list[RemediationConstraint]:
    constraints: list[RemediationConstraint] = []
    severity = "high" if compliance.risk == "HIGH" else "medium"
    for warning in reuse_warnings:
        constraints.append(
            RemediationConstraint(
                finding_type="duplicate_implementation",
                severity="medium",
                constraints=[
                    "Reuse the existing capability.",
                    "Do not introduce a parallel implementation.",
                ],
                evidence=[warning],
                requires_scope_amendment=[],
            )
        )
    for violation in compliance.violations:
        if violation.startswith("Unplanned production file:"):
            file = violation.split(":", 1)[1].strip()
            constraints.append(
                RemediationConstraint(
                    finding_type="scope_violation",
                    severity=severity,
                    constraints=[
                        "Keep changes inside the contract scope.",
                        (
                            "Request a scope amendment before modifying files "
                            "outside the contract."
                        ),
                    ],
                    evidence=[violation],
                    requires_scope_amendment=[file],
                )
            )
        elif violation.startswith("Modified explicitly avoided file:"):
            file = violation.split(":", 1)[1].strip()
            constraints.append(
                RemediationConstraint(
                    finding_type="scope_violation",
                    severity="high",
                    constraints=[
                        "Do not modify explicitly avoided files.",
                        "Request a scope amendment before touching them.",
                    ],
                    evidence=[violation],
                    requires_scope_amendment=[file],
                )
            )
        else:
            constraints.append(
                RemediationConstraint(
                    finding_type="compliance",
                    severity=severity,
                    constraints=["Resolve the contract violation."],
                    evidence=[violation],
                    requires_scope_amendment=[],
                )
            )
    return constraints


def format_complexity(signal: ComplexitySignal, contract: EngineeringContract) -> str:
    budget = contract.complexity_budget
    lines = [
        f"Complexity Signal: {signal.level}",
        "",
        "Complexity Budget:",
        (
            f"- preferred touched production files: "
            f"{budget.preferred_max_touched_production_files} | "
            f"actual: {signal.touched_production_files}"
        ),
        (
            f"- preferred new production files: "
            f"{budget.preferred_new_production_files} | "
            f"actual: {signal.new_production_files}"
        ),
        (
            f"- preferred new abstractions: "
            f"{budget.preferred_new_abstractions} | "
            f"actual new top-level classes: {signal.new_top_level_classes}"
        ),
        (
            f"- new top-level functions: {signal.new_top_level_functions} "
            "(informational)"
        ),
        (
            f"- dependency changes: "
            f"{'yes' if signal.dependency_changed else 'no'}"
        ),
    ]
    return "\n".join(lines)


def format_quality_signals(
    root: Path, result: ReviewResult
) -> str:
    symbols = _new_top_level_symbols(root, result)
    new_classes = sum(len(classes) for _, (classes, _) in symbols.items())
    new_functions = sum(len(funcs) for _, (_, funcs) in symbols.items())
    new_files = [
        p
        for p in result.added_paths
        if Path(p).suffix.lower() in SOURCE_EXTENSIONS and not _is_test_path(p)
    ]
    lines = [
        "Implementation Quality Signals:",
        f"- New production files: {len(new_files)}",
        f"- New top-level classes: {new_classes}",
        f"- New top-level functions: {new_functions}",
        (
            f"- Dependency files changed: "
            f"{'yes' if result.dependency_changed else 'no'}"
        ),
    ]
    for rel, (classes, functions) in symbols.items():
        names = classes + functions
        lines.append(f"- New symbols: {rel} :: {', '.join(names)}")
    return "\n".join(lines)


def format_remediation_constraints(
    constraints: list[RemediationConstraint],
) -> str:
    lines = ["Remediation Constraints:"]
    if not constraints:
        lines.append("- none")
        return "\n".join(lines)
    for constraint in constraints:
        lines.append(f"- {constraint.finding_type} ({constraint.severity})")
        lines.extend(f"  - {c}" for c in constraint.constraints)
        lines.extend(f"  evidence: {e}" for e in constraint.evidence)
        if constraint.requires_scope_amendment:
            lines.append(
                "  requires scope amendment: "
                + ", ".join(constraint.requires_scope_amendment)
            )
    return "\n".join(lines)


def format_plan_compliance(compliance: PlanCompliance) -> str:
    lines = [
        "Plan Compliance:",
        f"Status: {compliance.status}",
        "",
        "Goal:",
        compliance.goal,
        "",
    ]
    if compliance.approved_scope_amendments:
        lines.append("Original allowed production scope:")
        lines += (
            [f"- {p}" for p in compliance.original_allowed_scope]
            or ["- none"]
        )
        lines += ["", "Approved scope amendments:"]
        lines += [f"- {p}" for p in compliance.approved_scope_amendments]
        lines += ["", "Effective allowed production scope:"]
        lines += (
            [f"- {p}" for p in compliance.effective_allowed_scope]
            or ["- none"]
        )
    else:
        lines.append("Allowed production scope:")
        lines += [f"- {p}" for p in compliance.allowed_scope] or ["- none"]
    lines += ["", "Actual production changes:"]
    lines += [f"- {p}" for p in compliance.actual_changes] or ["- none"]
    if compliance.avoid_overridden:
        lines += [
            "",
            "Approved amendment overrides original Do Not Modify boundary:",
        ]
        lines += [f"- {p}" for p in compliance.avoid_overridden]
    if compliance.violations:
        lines += ["", "Violations:"]
        lines += [f"- {v}" for v in compliance.violations]
    if compliance.reuse_warnings:
        lines += ["", "Possible duplicate implementation:"]
        lines += [f"- {w}" for w in compliance.reuse_warnings]
    return "\n".join(lines)
