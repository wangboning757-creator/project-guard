"""Pre-implementation planning checks."""

from __future__ import annotations

import re
from pathlib import Path

from .models import PlanMatch, PlanResult
from .python_index import ModuleIndex, index_python_file
from .scanner import count_lines, iter_files

STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "in", "on", "with", "and", "or",
    "add", "implement", "support", "feature", "new", "our", "we", "it", "is",
    "should", "can", "do", "make", "into", "as", "at", "by", "from", "that",
    "this", "when", "using", "use", "need", "please", "want", "also", "not",
    "another", "more", "other",
}
SKIP_CONTENT_FILES = {
    "package-lock.json", "poetry.lock", "uv.lock", "Pipfile.lock",
}
MAX_CONTENT_LINES = 400
MAX_FILE_BYTES = 1_000_000
MAX_MATCHES = 20
ABSTRACT_BASE_NAMES = {"protocol", "abc", "abcmeta"}
MIN_ABSTRACTION_SIBLINGS = 2


def _is_test_path(rel: str) -> bool:
    parts = Path(rel).parts
    return (
        "tests" in parts
        or Path(rel).name.startswith("test_")
        or Path(rel).name.endswith("_test.py")
    )


def _is_source(rel: str) -> bool:
    return rel.endswith(".py") and not _is_test_path(rel)


def _is_init(path: str) -> bool:
    return Path(path).name == "__init__.py"


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
    return list(matches.values())


def _symbol_hits(index: ModuleIndex, keywords: list[str]) -> int:
    hits = 0
    for kw in keywords:
        if any(kw in c.lower() for c in index.classes):
            hits += 2
        if any(kw in f.lower() for f in index.functions):
            hits += 2
        if any(kw in i.lower() for i in index.imports):
            hits += 1
    return hits


def _find_abstraction(
    matches: list[PlanMatch], index: dict[str, ModuleIndex]
) -> tuple[str, set[str]] | None:
    dirs: dict[str, list[PlanMatch]] = {}
    for m in matches:
        if not _is_source(m.path):
            continue
        dirs.setdefault(m.path.rpartition("/")[0], []).append(m)
    candidates: list[PlanMatch] = []
    for files in dirs.values():
        base_file = next(
            (f for f in files if Path(f.path).stem == "base"), None
        )
        if base_file is None:
            continue
        idx = index.get(base_file.path)
        if idx is None:
            continue
        is_abstract = any(
            "provider" in c.lower() for c in idx.classes
        ) or any(b.lower() in ABSTRACT_BASE_NAMES for b in idx.bases)
        if not is_abstract:
            continue
        siblings = [
            f
            for f in files
            if f.path != base_file.path and not _is_init(f.path)
        ]
        if len(siblings) >= MIN_ABSTRACTION_SIBLINGS:
            candidates.append(base_file)
    if not candidates:
        return None
    best = max(candidates, key=lambda m: (m.symbol_hits, m.hits))
    base_classes = set(index[best.path].classes)
    d = best.path.rpartition("/")[0]
    impl_paths: set[str] = set()
    for m in matches:
        if not _is_source(m.path) or m.path == best.path:
            continue
        if m.path.rpartition("/")[0] != d:
            continue
        idx = index.get(m.path)
        if idx is not None:
            is_impl = any(
                "provider" in c.lower() for c in idx.classes
            ) or any(b in base_classes for b in idx.bases)
            if is_impl:
                impl_paths.add(m.path)
    return best.path, impl_paths


def analyze_plan(root: Path, request: str) -> PlanResult:
    root = root.resolve()
    keywords = _keywords(request)
    matches = _search(root, keywords)

    index: dict[str, ModuleIndex] = {}
    for m in matches:
        if not _is_source(m.path):
            continue
        idx = index_python_file(root / m.path, m.path)
        if idx is not None:
            index[m.path] = idx
            m.symbol_hits = _symbol_hits(idx, keywords)

    abstraction = _find_abstraction(matches, index)
    impl_paths = abstraction[1] if abstraction else set()
    ranked = sorted(
        matches,
        key=lambda m: (
            0 if _is_source(m.path) else 1,
            1 if m.path in impl_paths else 0,
            -m.symbol_hits,
            -m.hits,
            1 if _is_init(m.path) else 0,
            m.path,
        ),
    )[:MAX_MATCHES]

    source_matches = [m for m in ranked if _is_source(m.path)]
    duplication_risk = any(
        m.hits >= 3 or len(m.keywords) >= 2 for m in source_matches
    )
    if abstraction:
        base_path = abstraction[0]
        suggestion = (
            f"Existing provider abstraction detected in `{base_path}`. "
            "Follow the existing provider pattern instead of creating a new "
            "abstraction."
        )
    elif source_matches:
        top = source_matches[0]
        suggestion = (
            f"Existing code already touches this area. Start from the most "
            f"relevant module `{top.path}` and reuse its symbols; keep the "
            "change local and avoid touching unrelated modules."
        )
    elif matches:
        suggestion = (
            "Existing keyword hits are only in tests/docs - no source code "
            "implements this yet. Add a small new module (or extend the "
            "closest existing module) and keep the change local."
        )
    else:
        suggestion = (
            "No existing code appears to cover this request. Add a small new "
            "module (or extend the closest existing module) and keep the "
            "change local; avoid touching unrelated modules."
        )
    return PlanResult(
        request=request,
        keywords=keywords,
        matches=ranked,
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
            f"hits: {m.hits}, symbols: {m.symbol_hits}, lines: {m.lines})"
            for m in result.matches
        )
        lines.append("")
        lines.append("Likely affected files:")
        tests_requested = any("test" in k for k in result.keywords)
        likely = (
            result.matches
            if tests_requested
            else [m for m in result.matches if not _is_test_path(m.path)]
        )
        lines.extend(f"  - {m.path}" for m in likely[:5])
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
