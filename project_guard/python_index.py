"""Minimal Python symbol index built with the standard library ast module."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModuleIndex:
    path: str
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    top_functions: list[str] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)


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


def index_python_file(path: Path, rel: str) -> ModuleIndex | None:
    """Parse one .py file; returns None when the file cannot be parsed."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, OSError, ValueError):
        return None
    index = ModuleIndex(path=rel)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            index.top_functions.append(node.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            index.classes.append(node.name)
            for base in node.bases:
                name = _base_name(base)
                if name:
                    index.bases.append(name)
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
