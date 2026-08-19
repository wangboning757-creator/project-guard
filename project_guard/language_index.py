"""Small deterministic indexers for non-Python source files."""

from __future__ import annotations

import re

from .symbol_index import SymbolIndex

IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
JAVA_TYPE_RE = re.compile(
    r"\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)"
)
JAVA_METHOD_RE = re.compile(
    r"\b(?:public|private|protected|static|final|abstract|synchronized|native|default|\s)+"
    r"[\w$<>\[\],.?]+\s+([A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*\{"
)
JAVA_CONSTRUCTOR_RE = re.compile(
    r"\b([A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*\{"
)
JS_CLASS_RE = re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)")
JS_FUNCTION_RE = re.compile(
    r"\bfunction\s*([A-Za-z_$][\w$]*)\s*\(|"
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
    r"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>|"
    r"\b(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*\{"
)
GO_TYPE_RE = re.compile(r"\btype\s+([A-Za-z_][\w]*)\s+(struct|interface|[A-Za-z_][\w]*)")
GO_FUNC_RE = re.compile(
    r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][\w]*)\s*\("
)
RUST_TYPE_RE = re.compile(r"\b(?:struct|enum|trait)\s+([A-Za-z_][\w]*)")
RUST_FUNC_RE = re.compile(r"\bfn\s+([A-Za-z_][\w]*)\s*\(")
HTML_REF_RE = re.compile(
    r"\b(?:script\s+[^>]*src|link\s+[^>]*href|form\s+[^>]*action)"
    r"\s*=\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
HTML_ATTR_RE = re.compile(
    r"\b(?:id|class|data-[\w-]+|aria-[\w-]+)\s*=\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
HTML_TAG_RE = re.compile(r"<([a-z][a-z0-9-]*(?:-[a-z0-9-]+)+)\b", re.IGNORECASE)

CONTROL_NAMES = {
    "if", "for", "while", "switch", "catch", "with", "return",
}
COMMENT_RE = re.compile(r"//[^\r\n]*|/\*.*?\*/", re.DOTALL)
COMMENT_STRING_RE = re.compile(
    r"//[^\r\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|"
    r"'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`",
    re.DOTALL,
)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _identifiers(source: str) -> list[str]:
    return _unique(IDENTIFIER_RE.findall(source))


def _without_comments(source: str) -> str:
    return COMMENT_RE.sub(
        lambda match: "\n" * match.group(0).count("\n"), source
    )


def _without_comments_and_strings(source: str) -> str:
    return COMMENT_STRING_RE.sub(
        lambda match: "\n" * match.group(0).count("\n"), source
    )


def _add_import(values: list[str], value: str) -> None:
    value = value.strip()
    if not value:
        return
    values.append(value)
    tail = value.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
    if tail and tail != value:
        values.append(tail)


def _java_index(source: str, rel: str) -> SymbolIndex:
    index = SymbolIndex(path=rel, language="java")
    source_without_comments = _without_comments(source)
    structural_source = _without_comments_and_strings(source)
    package = re.search(r"\bpackage\s+([\w.]+)\s*;", source_without_comments)
    index.package = package.group(1) if package else None
    index.classes = _unique(JAVA_TYPE_RE.findall(structural_source))
    for kind, name in re.findall(
        r"\b(class|interface|enum|record)\s+([A-Za-z_$][\w$]*)",
        structural_source,
    ):
        if kind in {"interface", "record"}:
            index.abstract_symbols.append(name)
    for match in re.finditer(
        r"\b(?:extends|implements)\s+([A-Za-z_$][\w$]*(?:\s*,\s*[A-Za-z_$][\w$]*)*)",
        structural_source,
    ):
        index.bases.extend(re.findall(r"[A-Za-z_$][\w$]*", match.group(1)))
    for match in re.finditer(
        r"\bimport\s+(?:static\s+)?([^;]+);", source_without_comments
    ):
        _add_import(index.imports, match.group(1).strip())
    methods = JAVA_METHOD_RE.findall(structural_source)
    constructors = JAVA_CONSTRUCTOR_RE.findall(structural_source)
    index.functions = _unique(methods + [name for name in constructors if name in index.classes])
    index.top_functions = list(index.functions)
    index.identifiers = _identifiers(structural_source)
    index.exports = list(index.classes)
    if re.search(
        r"public\s+static\s+void\s+main\s*\(", structural_source
    ):
        index.entry_points.append("main")
    return index


def _javascript_index(source: str, rel: str, language: str) -> SymbolIndex:
    index = SymbolIndex(path=rel, language=language)
    source_without_comments = _without_comments(source)
    structural_source = _without_comments_and_strings(source)
    index.classes = _unique(JS_CLASS_RE.findall(structural_source))
    for match in re.finditer(
        r"\b(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)",
        structural_source,
    ):
        index.classes.append(match.group(1))
        index.abstract_symbols.append(match.group(1))
    for match in JS_FUNCTION_RE.finditer(structural_source):
        index.functions.extend(part for part in match.groups() if part)
    index.functions = [name for name in _unique(index.functions) if name not in CONTROL_NAMES]
    index.top_functions = list(index.functions)
    for match in re.finditer(
        r"(?m)^\s*import\s+(.*?)\s+from\s*[\"']([^\"']+)[\"']",
        source_without_comments,
        re.DOTALL,
    ):
        _add_import(index.imports, match.group(2))
        index.imports.extend(
            re.findall(r"[A-Za-z_$][\w$]*", match.group(1))
        )
    for match in re.finditer(
        r"(?m)^\s*import\s*[\"']([^\"']+)[\"']",
        source_without_comments,
    ):
        _add_import(index.imports, match.group(1))
    for match in re.finditer(
        r"\brequire\s*\(\s*[\"']([^\"']+)[\"']\s*\)",
        source_without_comments,
    ):
        _add_import(index.imports, match.group(1))
    for match in re.finditer(
        r"\bexport\s+(?:default\s+)?(?:class|function|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
        structural_source,
    ):
        index.exports.append(match.group(1))
    for match in re.finditer(r"\bexport\s*\{([^}]+)\}", structural_source):
        index.exports.extend(re.findall(r"[A-Za-z_$][\w$]*", match.group(1)))
    for match in re.finditer(
        r"\b(?:extends|implements)\s+([A-Za-z_$][\w$]*)", structural_source
    ):
        index.bases.append(match.group(1))
    index.identifiers = _identifiers(structural_source)
    index.classes = _unique(index.classes)
    index.imports = _unique(index.imports)
    index.exports = _unique(index.exports)
    index.bases = _unique(index.bases)
    if re.search(
        r"\b(?:function\s+)?main\s*\(", structural_source
    ) or rel.split("/")[-1] in {
        "cli.js", "cli.ts",
    }:
        index.entry_points.append("main")
    return index


def _go_index(source: str, rel: str) -> SymbolIndex:
    index = SymbolIndex(path=rel, language="go")
    source_without_comments = _without_comments(source)
    structural_source = _without_comments_and_strings(source)
    package = re.search(
        r"\bpackage\s+([A-Za-z_][\w]*)", source_without_comments
    )
    index.package = package.group(1) if package else None
    index.classes = [name for name, _ in GO_TYPE_RE.findall(structural_source)]
    for name, kind in GO_TYPE_RE.findall(structural_source):
        if kind == "interface":
            index.abstract_symbols.append(name)
    index.functions = _unique(GO_FUNC_RE.findall(structural_source))
    index.top_functions = list(index.functions)
    for match in re.finditer(
        r"\bimport\s+(?:\(\s*)?([^\n)]+)", source_without_comments
    ):
        chunk = match.group(1)
        for value in re.findall(r"[\"']([^\"']+)[\"']", chunk):
            _add_import(index.imports, value)
    index.identifiers = _identifiers(structural_source)
    if (
        re.search(r"\bpackage\s+main\b", structural_source)
        and "main" in index.functions
    ):
        index.entry_points.append("main")
    return index


def _rust_index(source: str, rel: str) -> SymbolIndex:
    index = SymbolIndex(path=rel, language="rust")
    source_without_comments = _without_comments(source)
    structural_source = _without_comments_and_strings(source)
    index.classes = _unique(RUST_TYPE_RE.findall(structural_source))
    index.abstract_symbols = _unique(
        re.findall(r"\btrait\s+([A-Za-z_][\w]*)", structural_source)
    )
    index.functions = _unique(RUST_FUNC_RE.findall(structural_source))
    index.top_functions = list(index.functions)
    for match in re.finditer(
        r"\b(?:use|mod)\s+([^;]+);", source_without_comments
    ):
        _add_import(index.imports, match.group(1).strip())
    for match in re.finditer(
        r"\bimpl\s+([A-Za-z_][\w]*(?:<[^>]+>)?)\s+for\s+([A-Za-z_][\w]*)",
        structural_source,
    ):
        index.bases.append(match.group(1))
    index.identifiers = _identifiers(structural_source)
    if "main" in index.functions or rel.endswith("/main.rs"):
        index.entry_points.append("main")
    return index


def _html_index(source: str, rel: str) -> SymbolIndex:
    index = SymbolIndex(path=rel, language="html")
    index.references = _unique(HTML_REF_RE.findall(source))
    index.references.extend(
        value for value in HTML_ATTR_RE.findall(source) if value
    )
    index.references = _unique(index.references)
    index.identifiers = _identifiers(source)
    index.classes = _unique(HTML_TAG_RE.findall(source))
    return index


def generic_index(source: str, rel: str) -> SymbolIndex:
    return SymbolIndex(
        path=rel,
        language="generic",
        identifiers=_identifiers(source)[:2000],
    )


def index_language_source(source: str, rel: str, language: str) -> SymbolIndex:
    if language == "java":
        return _java_index(source, rel)
    if language in {"javascript", "typescript"}:
        return _javascript_index(source, rel, language)
    if language == "go":
        return _go_index(source, rel)
    if language == "rust":
        return _rust_index(source, rel)
    if language == "html":
        return _html_index(source, rel)
    return generic_index(source, rel)
