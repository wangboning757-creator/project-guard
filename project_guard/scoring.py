"""Transparent rule-based readiness scoring."""

from __future__ import annotations

from pathlib import Path

from .config import (
    DEPENDENCY_SOFT_LIMIT,
    DIFF_HUGE_ADDITIONS,
    DIFF_LARGE_ADDITIONS,
    LARGE_FILE_LINES,
    MAX_DEPTH,
    VERY_LARGE_FILE_LINES,
)
from .models import ReviewResult, ScanResult, ScoreDeduction, ScoreResult


def _duplicate_stems(scan: ScanResult) -> list[tuple[str, list[str]]]:
    stem_map: dict[str, list[str]] = {}
    for f in scan.python_files:
        stem = Path(f.path).stem.lower()
        if stem in ("__init__", "__main__"):
            continue
        stem_map.setdefault(stem, []).append(f.path)
    return [(s, paths) for s, paths in stem_map.items() if len(paths) > 1]


def compute_score(
    scan: ScanResult, review: ReviewResult | None = None
) -> ScoreResult:
    deductions: list[ScoreDeduction] = []

    def add(rule: str, points: int, reason: str) -> None:
        deductions.append(
            ScoreDeduction(rule=rule, points=points, reason=reason)
        )

    giant = [f for f in scan.files if f.lines >= VERY_LARGE_FILE_LINES]
    oversized = [
        f
        for f in scan.files
        if LARGE_FILE_LINES <= f.lines < VERY_LARGE_FILE_LINES
    ]
    for f in giant[:3]:
        add("giant file", 8, f"{f.path} ({f.lines} lines)")
    for f in oversized[:3]:
        add("large file", 3, f"{f.path} ({f.lines} lines)")

    deps = scan.dependency_total
    if deps > DEPENDENCY_SOFT_LIMIT:
        points = min(10, (deps - DEPENDENCY_SOFT_LIMIT) // 5 * 2)
        add("dependency count", points, f"{deps} dependencies")

    if scan.max_depth > MAX_DEPTH:
        add("deep nesting", 5, f"max directory depth {scan.max_depth}")

    for stem, paths in _duplicate_stems(scan)[:2]:
        add("duplicate module name", 5, f"{stem}: {', '.join(paths)}")

    root = Path(scan.root)
    if not (root / "README.md").is_file():
        add("missing README", 5, "no README.md")
    if not (root / "pyproject.toml").is_file() and not (
        root / "setup.py"
    ).is_file():
        add("missing packaging", 5, "no pyproject.toml / setup.py")
    if not (root / "tests").is_dir():
        add("missing tests", 5, "no tests/ directory")

    if review is not None:
        if review.total_added >= DIFF_HUGE_ADDITIONS:
            add("large diff", 15, f"+{review.total_added} uncommitted lines")
        elif review.total_added >= DIFF_LARGE_ADDITIONS:
            add("large diff", 8, f"+{review.total_added} uncommitted lines")
        elif review.total_added >= 150:
            add("large diff", 3, f"+{review.total_added} uncommitted lines")

    score = max(0, 100 - sum(d.points for d in deductions))
    return ScoreResult(score=score, deductions=deductions)


def format_score(result: ScoreResult) -> str:
    lines = [f"AI Coding Readiness Score: {result.score}/100"]
    if result.deductions:
        lines.append("")
        lines.append("Deductions:")
        lines.extend(
            f"  - {d.rule} ({d.reason}): -{d.points}"
            for d in result.deductions
        )
    else:
        lines.append("No deductions - clean project.")
    return "\n".join(lines)
