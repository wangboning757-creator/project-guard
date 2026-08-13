"""Pre-implementation planning checks."""

from __future__ import annotations

import re
from pathlib import Path

from .models import PlanMatch, PlanResult
from .scanner import count_lines, iter_files

STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "in", "on", "with", "and", "or",
    "add", "implement", "support", "feature", "new", "our", "we", "it", "is",
    "should", "can", "do", "make", "into", "as", "at", "by", "from", "that",
    "this", "when", "using", "use", "need", "please", "want", "also", "not",
}
SKIP_CONTENT_FILES = {
    "package-lock.json", "poetry.lock", "uv.lock", "Pipfile.lock",
}
MAX_CONTENT_LINES = 400
MAX_FILE_BYTES = 1_000_000
MAX_MATCHES = 20


def _keywords(request: str) -> list[str]:
    words = re.findall(r"[a-z0-9_]+", request.lower())
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    expanded: list[str] = []
    for w in words:
        expanded.append(w)
        if "_" in w:
            expanded.extend(p for p in w.split("_") if len(p) > 2)
    return expanded


def _search(root: Path, keywords: list[str]) -> list[PlanMatch]:
    keyword_set = set(keywords)
    matches: dict[str, PlanMatch] = {}
    for path in iter_files(root):
        if path.name in SKIP_CONTENT_FILES:
            continue
        rel = path.relative_to(root).as_posix()
        low_name = path.name.lower()
        count = sum(low_name.count(k) for k in keyword_set)
        matched = [k for k in keyword_set if k in low_name]
        if count == 0:
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                with path.open("r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f):
                        if i >= MAX_CONTENT_LINES:
                            break
                        low = line.lower()
                        for k in keyword_set:
                            if k in low:
                                count += 1
                                if k not in matched:
                                    matched.append(k)
            except OSError:
                continue
        if count > 0:
            matches[rel] = PlanMatch(
                path=rel,
                keywords=sorted(matched),
                hits=count,
                lines=count_lines(path),
            )
    ranked = sorted(
        matches.values(), key=lambda m: (-m.hits, m.lines, m.path)
    )
    return ranked[:MAX_MATCHES]


def analyze_plan(root: Path, request: str) -> PlanResult:
    root = root.resolve()
    keywords = _keywords(request)
    matches = _search(root, keywords)
    duplication_risk = any(
        m.hits >= 3 or len(m.keywords) >= 2 for m in matches
    )
    if matches:
        smallest = min(matches, key=lambda m: m.lines)
        suggestion = (
            f"Existing code already touches this area. Extend the smallest "
            f"matching module `{smallest.path}` ({smallest.lines} lines) and "
            f"reuse its symbols instead of creating a new module."
        )
    else:
        suggestion = (
            "No existing code appears to cover this request. Add the smallest "
            "new module (or extend the closest existing module) and keep the "
            "change local; avoid touching unrelated modules."
        )
    return PlanResult(
        request=request,
        keywords=keywords,
        matches=matches,
        duplication_risk=duplication_risk,
        suggestion=suggestion,
    )


def format_plan(result: PlanResult) -> str:
    lines = [
        f"Request: {result.request}",
        f"Keywords: {', '.join(result.keywords) or '-'}",
        "",
    ]
    if result.matches:
        lines.append("Similar modules / features found:")
        lines.extend(
            f"  - {m.path} (keywords: {', '.join(m.keywords) or '-'}, "
            f"hits: {m.hits}, lines: {m.lines})"
            for m in result.matches
        )
        lines.append("")
        lines.append("Likely affected files:")
        lines.extend(f"  - {m.path}" for m in result.matches[:5])
    else:
        lines.append("No similar modules found.")
    lines += [
        "",
        f"Potential duplication: {'yes' if result.duplication_risk else 'no'}",
        "",
        "Suggestion:",
        f"  {result.suggestion}",
    ]
    return "\n".join(lines)
