"""Pre-implementation planning checks."""

from __future__ import annotations

import re
from pathlib import Path

from .models import (
    ComplexityBudget,
    EngineeringContract,
    PlanMatch,
    PlanResult,
    PlanSnapshot,
)
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
TEXT_HIT_CAP = 5
MIN_EVIDENCE_TOKEN_MATCHES = 2
TERM_ALIASES = {"authentication": {"auth"}}
CLI_KEYWORDS = {"cli", "command", "option", "flag"}
CLI_IMPORT_NAMES = {"typer", "click", "argparse"}
EXPANSION_INTENT_TERMS = {
    "provider", "vendor", "backend", "adapter", "implementation",
    "integration", "connector", "driver",
}
EXPANSION_INTENT_PHRASES = (
    "new search engine",
    "new llm",
    "another llm",
    "another provider",
    "support another",
    "add support for another",
)
PARAM_INTENT_TERMS = {
    "limit", "maximum", "minimum", "threshold", "count",
    "timeout", "batch", "size", "option", "flag",
}
AVOID_GENERIC_TOKENS = {
    "one", "more", "set", "get", "add", "option", "flag", "command",
    "research", "search", "run", "used", "use", "result", "results",
    "number", "count", "limit", "maximum", "minimum", "timeout",
    "size", "batch", "list", "data", "value", "values", "enable",
    "disable", "config", "setting", "settings", "output", "path",
    "format", "threshold", "support", "feature", "new", "item",
    "items", "type", "types", "name", "names", "ids",
}
INTEGRATION_STEMS = {
    "factory", "settings", "config", "registry", "client",
    "workflow", "runtime", "cli", "main", "routes",
}
WIRING_STEMS = {"factory", "registry", "runtime"}
CONSTRUCTION_FUNCTION_HINTS = ("create", "build", "make", "get", "load")
REUSE_GOAL_PHRASES = ("reuse", "use existing", "reuse existing", "instead of")


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


def _has_abstraction_expansion_intent(
    request: str, keywords: list[str]
) -> bool:
    lowered = request.lower()
    if any(phrase in lowered for phrase in EXPANSION_INTENT_PHRASES):
        return True
    return any(k in EXPANSION_INTENT_TERMS for k in keywords)


def _has_cli_intent(request: str, keywords: list[str]) -> bool:
    return any(k in CLI_KEYWORDS for k in keywords)


def _has_parameter_change_intent(
    request: str, keywords: list[str]
) -> bool:
    return any(k in PARAM_INTENT_TERMS for k in keywords)


def _has_reuse_goal_intent(request: str) -> bool:
    lowered = request.lower()
    return any(phrase in lowered for phrase in REUSE_GOAL_PHRASES)


def _terms_for(keyword: str) -> set[str]:
    return {keyword} | TERM_ALIASES.get(keyword, set())


def _search(root: Path, keywords: list[str]) -> list[PlanMatch]:
    term_map: dict[str, str] = {}
    search_terms: set[str] = set()
    for kw in keywords:
        for term in _terms_for(kw):
            search_terms.add(term)
            term_map.setdefault(term, kw)
    matches: dict[str, PlanMatch] = {}
    for path in iter_files(root):
        if path.name in SKIP_CONTENT_FILES:
            continue
        rel = path.relative_to(root).as_posix()
        low_name = path.name.lower()
        count = sum(low_name.count(t) for t in search_terms)
        matched = {term_map[t] for t in search_terms if t in low_name}
        if count == 0:
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                with path.open("r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f):
                        if i >= MAX_CONTENT_LINES:
                            break
                        low = line.lower()
                        for t in search_terms:
                            if t in low:
                                count += 1
                                matched.add(term_map[t])
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


def _normalize_stem(stem: str) -> str:
    return stem.lstrip("_").replace("_", " ").lower()


def _ownership_score(path: str, keywords: list[str]) -> int:
    """+1 per keyword that names the module file itself (e.g. decoder in decoders.py)."""
    norm = _normalize_stem(Path(path).stem)
    score = 0
    for kw in keywords:
        if len(kw) < 4:
            continue
        terms = _terms_for(kw)
        if any(t in norm or norm in t for t in terms):
            score += 1
    return score


def _cli_entry_modules(root: Path) -> set[str]:
    """Rel paths of modules referenced by console scripts in pyproject.toml."""
    modules: set[str] = set()
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return modules
    in_scripts = False
    for raw in pyproject.read_text(
        encoding="utf-8", errors="ignore"
    ).splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_scripts = line in (
                "[project.scripts]", "[tool.poetry.scripts]",
            )
            continue
        if in_scripts and "=" in line:
            target = line.partition("=")[2].strip().strip('"').strip("'")
            module = target.split(":", 1)[0].strip()
            if module:
                modules.add(module.replace(".", "/") + ".py")
    return modules


def _cli_ownership(
    path: str,
    keywords: list[str],
    entry_modules: set[str],
    index: dict[str, ModuleIndex],
) -> int:
    if not any(k in CLI_KEYWORDS for k in keywords):
        return 0
    if path in entry_modules:
        return 1
    idx = index.get(path)
    if idx is None:
        return 0
    if "main" in idx.functions:
        return 1
    if any(i in CLI_IMPORT_NAMES for i in idx.imports):
        return 1
    return 0


def _is_integration(path: str, cli_owner: int) -> bool:
    stem = Path(path).stem.lstrip("_").lower()
    return stem in INTEGRATION_STEMS or cli_owner > 0


def _imports_owner(
    m: PlanMatch,
    owner_path: str,
    index: dict[str, ModuleIndex],
) -> bool:
    """True when this file imports a symbol defined in the owner module."""
    owner_idx = index.get(owner_path)
    cand_idx = index.get(m.path)
    if owner_idx is None or cand_idx is None:
        return False
    owner_names = {c.lower() for c in owner_idx.classes}
    owner_names |= {f.lower() for f in owner_idx.functions}
    owner_names.add(Path(owner_path).stem.lstrip("_").lower())
    cand_imports = {i.lower() for i in cand_idx.imports}
    return bool(owner_names & cand_imports)


_CAMEL_SPLIT = re.compile(
    r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+"
)


def _identifier_tokens(identifier: str) -> set[str]:
    """Normalize a snake_case / CamelCase identifier into lowercase tokens."""
    tokens: set[str] = set()
    for part in re.split(r"[_\-\s]+", identifier):
        for token in _CAMEL_SPLIT.findall(part):
            if token:
                tokens.add(token.lower())
    return tokens


def _token_overlap(a: set[str], b: set[str]) -> int:
    """Count tokens in b matched by any token in a (exact or substring)."""
    return sum(
        1
        for tb in b
        if any(ta in tb or tb in ta for ta in a)
    )


def _goal_evidence_tokens(request: str) -> set[str]:
    """Specific goal tokens (generic words filtered) for avoid protection."""
    tokens: set[str] = set()
    for word in re.findall(r"[a-z0-9_]+", request.lower()):
        if (
            word in STOPWORDS
            or word in AVOID_GENERIC_TOKENS
            or len(word) <= 2
        ):
            continue
        tokens.add(word)
        if "_" in word:
            tokens.update(
                p
                for p in word.split("_")
                if len(p) > 2 and p not in AVOID_GENERIC_TOKENS
            )
    return tokens


def _has_direct_capability_evidence(
    path: str,
    goal_tokens: set[str],
    index: dict[str, ModuleIndex],
) -> bool:
    """True when a file defines identifiers matching >=2 specific goal tokens.

    Only used to keep direct capability owners out of avoid_modifying.
    """
    idx = index.get(path)
    if idx is None or not goal_tokens:
        return False
    names = (
        set(idx.classes)
        | set(idx.functions)
        | set(idx.imports)
        | set(idx.identifiers)
    )
    return any(
        len(_identifier_tokens(name) & goal_tokens)
        >= MIN_EVIDENCE_TOKEN_MATCHES
        for name in names
    )


def _has_construction_signal(idx: ModuleIndex, path: str) -> bool:
    stem = Path(path).stem.lstrip("_").lower()
    if stem in WIRING_STEMS:
        return True
    return any(
        any(hint in fn.lower() for hint in CONSTRUCTION_FUNCTION_HINTS)
        for fn in idx.functions
    )


def _find_capability_wiring_points(
    ranked_source: list[PlanMatch],
    cap_files: list[str],
    index: dict[str, ModuleIndex],
    goal_tokens: set[str],
) -> list[str]:
    """Files that construct/inject a known capability owner (factory-like)."""
    owner_names: set[str] = set()
    for cap in cap_files:
        idx = index.get(cap)
        if idx is not None:
            owner_names |= set(idx.classes)
            owner_names |= set(idx.functions)
            owner_names.add(Path(cap).stem.lstrip("_").lower())
    if not owner_names:
        return []
    owner_lower = {n.lower() for n in owner_names}
    points: list[str] = []
    for m in ranked_source:
        idx = index.get(m.path)
        if idx is None:
            continue
        imports = {i.lower() for i in idx.imports}
        if not (imports & owner_lower):
            continue
        if not _has_construction_signal(idx, m.path):
            continue
        names = (
            set(idx.classes)
            | set(idx.functions)
            | set(idx.imports)
            | set(idx.identifiers)
        )
        if not any(
            _token_overlap(_identifier_tokens(n), goal_tokens) >= 1
            for n in names
        ):
            continue
        points.append(m.path)
    return points


def build_engineering_contract(
    request: str,
    keywords: list[str],
    snapshot: PlanSnapshot,
    ranked: list[PlanMatch],
    index: dict[str, ModuleIndex],
    entry_modules: set[str],
) -> EngineeringContract:
    """Derive an immutable Engineering Contract from planner evidence."""
    goal_tokens = _goal_evidence_tokens(request)
    ranked_source = [
        m
        for m in ranked
        if _is_source(m.path) and not _is_init(m.path)
    ]
    cap_files = snapshot.existing_capability_files
    wiring = (
        _find_capability_wiring_points(
            ranked_source, cap_files, index, goal_tokens
        )
        if cap_files
        else []
    )
    cli_intent = _has_cli_intent(request, keywords)
    cli_entry = next(
        (
            m.path
            for m in ranked_source
            if _cli_ownership(m.path, keywords, entry_modules, index) > 0
        ),
        None,
    )

    facts: list[str] = []
    if cli_entry:
        facts.append(f"CLI entry point detected: {cli_entry}")
    for cap in cap_files:
        facts.append(f"Existing capability detected: {cap}")
    for point in wiring:
        facts.append(f"Provider construction detected: {point}")
    if not facts:
        facts.append("No high-confidence structural facts found.")

    return EngineeringContract(
        original_request=request,
        # Preserved copy of the explicit user request. Project Guard does
        # not claim to have decomposed or semantically validated it.
        explicit_requirements=[request],
        inferred_requirements=[
            "Preserve existing behavior outside the requested change.",
            "Reuse existing capability where available.",
            "Avoid unrelated refactoring.",
            "Do not add dependencies or abstractions unless required by "
            "the current goal.",
        ],
        # Project Guard does not guess business scope or product ambiguity.
        # The Coding Agent forms assumptions and unresolved questions.
        assumptions=[],
        unresolved_questions=[],
        repository_facts=facts,
        recommended_scope=snapshot.recommended_scope,
        possible_scope=snapshot.possible_scope,
        avoid_modifying=snapshot.avoid_modifying,
        existing_capability_files=cap_files,
        new_dependency=snapshot.new_dependency,
        new_abstraction=snapshot.new_abstraction,
        refactor=snapshot.refactor,
        complexity_budget=ComplexityBudget(),
        testing_policy=(
            "Run targeted tests for the behavior directly affected by the "
            "change; expand scope only when shared interfaces or multiple "
            "core modules are affected."
        ),
    )


def _capability_keyword(
    m: PlanMatch, keywords: list[str], index: dict[str, ModuleIndex]
) -> str | None:
    """First keyword this file owns via filename or class/function names."""
    norm = _normalize_stem(Path(m.path).stem)
    idx = index.get(m.path)
    for kw in keywords:
        terms = _terms_for(kw)
        if any(t in norm or norm in t for t in terms):
            return kw
        if idx is not None and (
            any(any(t in c.lower() for t in terms) for c in idx.classes)
            or any(
                any(t in f.lower() for t in terms) for f in idx.functions
            )
        ):
            return kw
    return None


def _symbol_hits(
    index: ModuleIndex, keywords: list[str]
) -> tuple[int, int]:
    """Return (definition hits, import hits) for ranking."""
    def_hits = 0
    import_hits = 0
    for kw in keywords:
        terms = _terms_for(kw)
        if any(any(t in c.lower() for t in terms) for c in index.classes):
            def_hits += 1
        if any(any(t in f.lower() for t in terms) for f in index.functions):
            def_hits += 1
        if any(any(t in i.lower() for t in terms) for i in index.imports):
            import_hits += 1
    return def_hits, import_hits


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


def _build_guardrail(
    request: str,
    keywords: list[str],
    ranked: list[PlanMatch],
    index: dict[str, ModuleIndex],
    symbol_scores: dict[str, tuple[int, int]],
    abstraction: tuple[str, set[str]] | None,
    impl_paths: set[str],
    entry_modules: set[str],
) -> tuple[str, PlanSnapshot]:
    cli_intent = _has_cli_intent(request, keywords)
    param_intent = _has_parameter_change_intent(request, keywords)
    goal_tokens = _goal_evidence_tokens(request)
    ranked_source = [
        m
        for m in ranked
        if _is_source(m.path)
        and not _is_init(m.path)
        and m.path not in impl_paths
    ]

    scope_paths: list[str] = []
    scope_lines: list[str] = []
    reuse_goal = False
    wiring_points: set[str] = set()
    if abstraction:
        base_path = abstraction[0]
        scope_paths.append(base_path)
        for m in ranked_source:
            stem = Path(m.path).stem
            if (
                stem in ("factory", "settings", "config")
                and m.path not in scope_paths
            ):
                scope_paths.append(m.path)
        scope_paths = scope_paths[:3]
        scope_lines.append(
            f"  - {scope_paths[0]} only if interface change is required"
        )
        scope_lines.extend(f"  - {p}" for p in scope_paths[1:])
        scope_lines.append(
            "  - new provider module only if implementation requires it"
        )
    else:
        ordered = ranked_source
        if cli_intent:
            cli_files = [
                m
                for m in ranked_source
                if _cli_ownership(m.path, keywords, entry_modules, index) > 0
            ]
            if cli_files:
                top = cli_files[0]
                ordered = [top] + [
                    m for m in ranked_source if m.path != top.path
                ]
        recommended = ordered[0] if ordered else None
        cap_files = sorted(
            m.path
            for m in ranked_source
            if m.path != (recommended.path if recommended else None)
            and _has_direct_capability_evidence(
                m.path, goal_tokens, index
            )
        )
        reuse_goal = _has_reuse_goal_intent(request) or bool(
            cap_files and (param_intent or cli_intent)
        )
        if reuse_goal and cap_files:
            wiring_points = set(
                _find_capability_wiring_points(
                    ranked_source, cap_files, index, goal_tokens
                )
            )
        if recommended is not None:
            scope_paths.append(recommended.path)
        for m in ordered:
            if len(scope_paths) >= 3:
                break
            if m.path != scope_paths[0] and m.path in wiring_points:
                scope_paths.append(m.path)
        owner_path = scope_paths[0] if scope_paths else None
        for m in ordered:
            if len(scope_paths) >= 3:
                break
            if m.path in scope_paths:
                continue
            cli_owner = _cli_ownership(
                m.path, keywords, entry_modules, index
            )
            if (
                _ownership_score(m.path, keywords) > 0
                or (
                    _is_integration(m.path, cli_owner)
                    and (
                        cli_owner > 0
                        or (
                            owner_path is not None
                            and _imports_owner(m, owner_path, index)
                        )
                        or (
                            param_intent
                            and symbol_scores.get(m.path, (0, 0))[0] > 0
                        )
                    )
                )
            ):
                scope_paths.append(m.path)
        scope_lines = [
            f"  - {p}" if i == 0 else f"  - possibly {p}"
            for i, p in enumerate(scope_paths)
        ]

    avoid = [
        m
        for m in ranked_source
        if m.path not in scope_paths
        and m.hits >= 3
        and _ownership_score(m.path, keywords) == 0
        and Path(m.path).stem.lstrip("_").lower() not in INTEGRATION_STEMS
        and not _has_direct_capability_evidence(
            m.path, goal_tokens, index
        )
    ][:3]
    avoid_lines = [f"  - {m.path}" for m in avoid] or [
        "  - none - no strong signal"
    ]
    recommended_path = scope_paths[0] if scope_paths else None
    snapshot_cap_files = sorted(
        m.path
        for m in ranked_source
        if m.path != recommended_path
        and m.path not in wiring_points
        and _has_direct_capability_evidence(
            m.path, goal_tokens, index
        )
    )

    if abstraction:
        base_path = abstraction[0]
        factory = next(
            (p for p in scope_paths if Path(p).stem == "factory"), None
        )
        reuse = f"Existing provider abstraction in {base_path}"
        if factory:
            reuse += f" and provider creation path in {factory}"
        reuse += "."
    elif snapshot_cap_files and reuse_goal:
        reuse = (
            f"Existing capability in {snapshot_cap_files[0]}. "
            "Reuse it instead of creating a parallel mechanism."
        )
    elif scope_paths:
        top = next(m for m in ranked_source if m.path == scope_paths[0])
        cli_owner = _cli_ownership(
            top.path, keywords, entry_modules, index
        )
        if cli_owner:
            reuse = (
                f"Existing CLI entry point in {scope_paths[0]}. "
                "Reuse it instead of creating a parallel mechanism."
            )
        elif kw := _capability_keyword(top, keywords, index):
            reuse = (
                f"Existing {kw} implementation in {scope_paths[0]}. "
                "Reuse it instead of creating a parallel mechanism."
            )
        else:
            reuse = (
                f"Existing implementation in {scope_paths[0]}. "
                "Reuse it instead of creating a parallel mechanism."
            )
    else:
        reuse = "No strong signal"

    if any("sdk" in k for k in keywords) or "new dependency" in request.lower():
        dep = "potentially justified"
    else:
        dep = "not justified"

    if abstraction:
        abs_text = "reuse existing abstraction"
    elif scope_paths:
        idx = index.get(scope_paths[0])
        abs_text = (
            f"reuse existing structure in {scope_paths[0]}"
            if idx is not None and idx.bases
            else "not justified"
        )
    else:
        abs_text = "not justified"

    refactor = "not justified"
    if scope_paths:
        top_path = scope_paths[0]
        idx = index.get(top_path)
        def_hits = symbol_scores.get(top_path, (0, 0))[0]
        if (
            idx is not None
            and len(idx.top_functions) >= 4
            and _ownership_score(top_path, keywords) == 0
            and def_hits == 0
        ):
            refactor = "no strong signal"

    if abstraction:
        reason = (
            f"Existing provider abstraction detected in {abstraction[0]}; "
            "follow the existing pattern and keep the change local."
        )
    elif scope_paths:
        reason = (
            f"Capability ownership is strongest in {scope_paths[0]}; other "
            "matches are usage or integration sites. Keep the change local."
        )
        if refactor == "no strong signal":
            reason += " No reliable structure signal for refactor judgment."
    else:
        reason = "No similar modules found; no architecture signal."

    text = "\n".join(
        [
            "Implementation Guardrail:",
            "",
            "Goal:",
            request,
            "",
            "Recommended change scope:",
            *(scope_lines or ["  - none"]),
            "",
            "Avoid modifying:",
            *avoid_lines,
            "",
            "Existing capability to reuse:",
            reuse,
            "",
            "New dependency:",
            dep,
            "",
            "New abstraction:",
            abs_text,
            "",
            "Refactor:",
            refactor,
            "",
            "Reason:",
            reason,
        ]
    )
    snapshot = PlanSnapshot(
        goal=request,
        recommended_scope=scope_paths[:1],
        possible_scope=scope_paths[1:],
        avoid_modifying=[m.path for m in avoid],
        new_dependency=dep,
        new_abstraction=abs_text,
        refactor=refactor,
        existing_capability_files=snapshot_cap_files,
    )
    return text, snapshot


def analyze_plan(root: Path, request: str) -> PlanResult:
    root = root.resolve()
    keywords = _keywords(request)
    matches = _search(root, keywords)

    index: dict[str, ModuleIndex] = {}
    symbol_scores: dict[str, tuple[int, int]] = {}
    for m in matches:
        if not _is_source(m.path):
            continue
        idx = index_python_file(root / m.path, m.path)
        if idx is not None:
            index[m.path] = idx
            symbol_scores[m.path] = _symbol_hits(idx, keywords)
            def_hits, import_hits = symbol_scores[m.path]
            m.symbol_hits = def_hits * 2 + import_hits

    expansion_intent = _has_abstraction_expansion_intent(request, keywords)
    abstraction = (
        _find_abstraction(matches, index) if expansion_intent else None
    )
    impl_paths = abstraction[1] if abstraction else set()
    entry_modules = _cli_entry_modules(root)

    def _rank_key(m: PlanMatch) -> tuple:
        def_hits, import_hits = symbol_scores.get(m.path, (0, 0))
        ownership = _ownership_score(m.path, keywords)
        ownership += _cli_ownership(
            m.path, keywords, entry_modules, index
        )
        return (
            0 if _is_source(m.path) else 1,
            1 if m.path in impl_paths else 0,
            -ownership,
            -def_hits,
            -import_hits,
            -min(m.hits, TEXT_HIT_CAP),
            1 if _is_init(m.path) else 0,
            m.path,
        )

    ranked = sorted(matches, key=_rank_key)[:MAX_MATCHES]

    source_matches = [m for m in ranked if _is_source(m.path)]
    duplication_risk = abstraction is not None
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
    guardrail, snapshot = _build_guardrail(
        request,
        keywords,
        ranked,
        index,
        symbol_scores,
        abstraction,
        impl_paths,
        entry_modules,
    )
    contract = build_engineering_contract(
        request,
        keywords,
        snapshot,
        ranked,
        index,
        entry_modules,
    )
    return PlanResult(
        request=request,
        keywords=keywords,
        matches=ranked,
        duplication_risk=duplication_risk,
        suggestion=suggestion,
        guardrail=guardrail,
        snapshot=snapshot,
        contract=contract,
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
    if result.guardrail:
        lines += ["", result.guardrail]
    return "\n".join(lines)
