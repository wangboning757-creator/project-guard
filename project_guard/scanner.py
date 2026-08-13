"""Filesystem scanning for project-guard."""

from __future__ import annotations

import json
from pathlib import Path

from .config import IGNORED_DIRS, MAX_TOP_DIRS
from .models import DependencySummary, DirSummary, FileInfo, ScanResult


def _is_ignored(path: Path, root: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.relative_to(root).parts)


def count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not _is_ignored(path, root):
            yield path


def _requirements_names(path: Path) -> list[str]:
    names = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        names.append(line.split()[0])
    return names


def _pyproject_dependency_names(path: Path) -> list[str]:
    names: list[str] = []
    in_project = False
    in_deps_array = False
    in_poetry = False
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_project = line == "[project]"
            in_poetry = line == "[tool.poetry.dependencies]"
            in_deps_array = False
            continue
        if in_poetry:
            if line.startswith("python") or not line:
                continue
            name = line.split("=", 1)[0].strip().strip('"')
            if name:
                names.append(name)
        elif in_project:
            if in_deps_array:
                item = line.strip(",").strip("\"'")
                if item and item != "]":
                    names.append(item)
                if "]" in line:
                    in_deps_array = False
            elif "dependencies" in line and "=" in line:
                in_deps_array = "[" in line and "]" not in line
                chunk = line.split("[", 1)[-1].split("]", 1)[0]
                for item in chunk.split(","):
                    item = item.strip().strip("\"'")
                    if item:
                        names.append(item)
    return names


def _package_json_names(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except ValueError:
        return []
    names = []
    for key in ("dependencies", "devDependencies"):
        deps = data.get(key)
        if isinstance(deps, dict):
            names.extend(deps.keys())
    return names


def _scan_dependencies(root: Path) -> list[DependencySummary]:
    result: list[DependencySummary] = []

    def add(source: str, names: list[str]) -> None:
        if names:
            result.append(
                DependencySummary(source=source, count=len(names), names=names)
            )

    req = root / "requirements.txt"
    if req.is_file():
        add("requirements.txt", _requirements_names(req))
    req_dir = root / "requirements"
    if req_dir.is_dir():
        for p in sorted(req_dir.glob("*.txt")):
            add(p.name, _requirements_names(p))
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        add("pyproject.toml", _pyproject_dependency_names(pyproject))
    package_json = root / "package.json"
    if package_json.is_file():
        add("package.json", _package_json_names(package_json))
    return result


def scan_project(root: Path) -> ScanResult:
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")
    files: list[FileInfo] = []
    dir_counts: dict[str, int] = {}
    max_depth = 0
    for path in iter_files(root):
        rel = path.relative_to(root)
        files.append(FileInfo(path=rel.as_posix(), lines=count_lines(path)))
        max_depth = max(max_depth, len(rel.parts))
        if len(rel.parts) > 1:
            top = rel.parts[0]
            dir_counts[top] = dir_counts.get(top, 0) + 1

    files.sort(key=lambda f: (-f.lines, f.path))
    top_dirs = [
        DirSummary(path=name, file_count=count)
        for name, count in sorted(
            dir_counts.items(), key=lambda kv: (-kv[1], kv[0])
        )[:MAX_TOP_DIRS]
    ]
    return ScanResult(
        root=str(root),
        file_count=len(files),
        python_file_count=sum(1 for f in files if f.path.endswith(".py")),
        total_lines=sum(f.lines for f in files),
        max_depth=max_depth,
        files=files,
        top_dirs=top_dirs,
        dependencies=_scan_dependencies(root),
    )


def format_inspect(scan: ScanResult) -> str:
    lines = [
        f"Project: {scan.root}",
        f"Files: {scan.file_count} (Python: {scan.python_file_count})",
        f"Total lines: {scan.total_lines:,}",
    ]
    largest = scan.largest_file
    if largest:
        lines.append(f"Largest file: {largest.path} ({largest.lines:,} lines)")
    else:
        lines.append("Largest file: -")
    if scan.large_files:
        lines.append("Oversized files (>=500 lines):")
        lines.extend(
            f"  - {f.path}: {f.lines:,} lines" for f in scan.large_files
        )
    else:
        lines.append("Oversized files: none")
    if scan.top_dirs:
        lines.append("Main directories:")
        lines.extend(
            f"  - {d.path}: {d.file_count} files" for d in scan.top_dirs
        )
    lines.append(f"Dependencies: {scan.dependency_total}")
    for dep in scan.dependencies:
        lines.append(f"  - {dep.source}: {dep.count}")
    return "\n".join(lines)
