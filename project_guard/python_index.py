"""Minimal Python symbol index built with the standard library ast module."""

from __future__ import annotations

import ast
from pathlib import Path

from .symbol_index import SymbolIndex

# Compatibility alias for existing internal imports and callers.
ModuleIndex = SymbolIndex


def _base_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _collect_args(node: ast.FunctionDef | ast.AsyncFunctionDef, index: ModuleIndex) -> None:
    args = node.args
    for arg in args.posonlyargs + args.args + args.kwonlyargs:
        index.identifiers.append(arg.arg)
    if args.vararg:
        index.identifiers.append(args.vararg.arg)
    if args.kwarg:
        index.identifiers.append(args.kwarg.arg)


def _collect_target(target: ast.AST, index: ModuleIndex) -> None:
    if isinstance(target, ast.Name):
        index.identifiers.append(target.id)
    elif isinstance(target, ast.Attribute):
        index.identifiers.append(target.attr)


def index_python_source(source: str, rel: str) -> ModuleIndex | None:
    """Parse Python source text; returns None when it cannot be parsed."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, OSError, ValueError):
        return None
    index = ModuleIndex(path=rel, language="python")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            index.top_functions.append(node.name)
    index.entry_points = (
        ["main"] if "main" in index.top_functions or rel.endswith("/__main__.py") else []
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            index.classes.append(node.name)
            for base in node.bases:
                name = _base_name(base)
                if name:
                    index.bases.append(name)
                    if name.lower() in {"protocol", "abc", "abcmeta"}:
                        index.abstract_symbols.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            index.functions.append(node.name)
            _collect_args(node, index)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _collect_target(target, index)
        elif isinstance(node, ast.AnnAssign):
            _collect_target(node.target, index)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                index.imports.append(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                index.imports.append(node.module.split(".", 1)[0])
            for alias in node.names:
                if alias.name != "*":
                    index.imports.append(alias.name)
    return index


def index_python_file(path: Path, rel: str) -> ModuleIndex | None:
    """Parse one .py file; returns None when the file cannot be parsed."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    return index_python_source(source, rel)
