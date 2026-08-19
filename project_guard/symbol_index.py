"""Language-aware lightweight structural indexes.

The index is intentionally smaller than an AST or compiler model.  It stores
only deterministic evidence that the planner and reviewer can use to find
existing capability, wiring, and likely ownership.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MAX_INDEX_BYTES = 1_000_000

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".html": "html",
    ".htm": "html",
}


@dataclass
class SymbolIndex:
    path: str
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    # Kept in the historical position for ModuleIndex positional callers.
    top_functions: list[str] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)
    language: str = "generic"
    exports: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    abstract_symbols: list[str] = field(default_factory=list)
    package: str | None = None


def language_for_path(path: str | Path) -> str | None:
    return LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower())


def _read_source(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_INDEX_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _generic_index(source: str, rel: str) -> SymbolIndex:
    from .language_index import generic_index

    return generic_index(source, rel)


def index_source_file(path: Path, rel: str) -> SymbolIndex | None:
    """Index one source file without allowing parser failures to escape."""
    language = language_for_path(rel)
    if language == "python":
        from .python_index import index_python_file

        return index_python_file(path, rel)
    source = _read_source(path)
    if source is None:
        return None
    if language is None:
        return _generic_index(source, rel)
    try:
        from .language_index import index_language_source

        return index_language_source(source, rel, language)
    except (OSError, ValueError, TypeError, UnicodeError):
        return None


def index_source_text(source: str, rel: str) -> SymbolIndex | None:
    """Index source already loaded by a diff/review operation."""
    language = language_for_path(rel)
    if language is None:
        return _generic_index(source, rel)
    try:
        if language == "python":
            from .python_index import index_python_source

            return index_python_source(source, rel)
        from .language_index import index_language_source

        return index_language_source(source, rel, language)
    except (OSError, ValueError, TypeError, UnicodeError):
        return None
