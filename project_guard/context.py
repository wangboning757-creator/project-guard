"""Generate a compact Markdown context for coding agents."""

from __future__ import annotations

from pathlib import Path

from .models import FileInfo, ScanResult

ENTRY_NAMES = {
    "main.py", "cli.py", "__main__.py", "app.py",
    "manage.py", "server.py", "wsgi.py",
}
RULES_FILES = ("AGENTS.md", "CLAUDE.md")


def _entry_points(root: Path, scan: ScanResult) -> list[str]:
    entries: list[str] = []
    for f in scan.python_files:
        if f.path.split("/")[-1] in ENTRY_NAMES:
            entries.append(f"`{f.path}`")
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
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
                name, _, target = line.partition("=")
                entries.append(
                    f"console script `{name.strip()}` -> {target.strip()}"
                )
    seen: set[str] = set()
    unique = []
    for entry in entries:
        if entry not in seen:
            seen.add(entry)
            unique.append(entry)
    return unique


def _project_rules(root: Path) -> str:
    for name in RULES_FILES:
        path = root / name
        if path.is_file():
            body = "\n".join(
                path.read_text(
                    encoding="utf-8", errors="ignore"
                ).splitlines()[:60]
            )
            return f"(from {name}, first 60 lines)\n\n{body}"
    return "No AGENTS.md / CLAUDE.md found. Consider adding AGENTS.md with project-specific rules."


def _main_modules(scan: ScanResult, limit: int = 10) -> list[FileInfo]:
    return [f for f in scan.python_files if f.lines > 0][:limit]


def _deps_text(scan: ScanResult) -> str:
    if not scan.dependencies:
        return "none detected"
    parts = []
    for dep in scan.dependencies:
        names = ", ".join(dep.names[:25])
        if len(dep.names) > 25:
            names += ", ..."
        parts.append(f"- {dep.source} ({dep.count}): {names}")
    return "\n".join(parts)


def build_context(root: Path, scan: ScanResult) -> str:
    root = root.resolve()
    entries = _entry_points(root, scan)
    mods = [f"- `{f.path}` ({f.lines:,} lines)" for f in _main_modules(scan)]
    top_dirs = ", ".join(
        f"{d.path} ({d.file_count})" for d in scan.top_dirs
    ) or "-"
    sections = [
        f"# Project Context: {root.name or root}",
        "",
        "## Overview",
        f"- Files: {scan.file_count} (Python: {scan.python_file_count})",
        f"- Total lines: {scan.total_lines:,}",
        f"- Max directory depth: {scan.max_depth}",
        f"- Main directories: {top_dirs}",
        "",
        "## Entry Points",
    ]
    sections += entries or ["- none detected"]
    sections += [
        "",
        "## Main Modules",
    ]
    sections += mods or ["- none detected"]
    sections += [
        "",
        "## Dependencies",
        _deps_text(scan),
        "",
        "## Project Rules",
        _project_rules(root),
        "",
    ]
    return "\n".join(sections)
