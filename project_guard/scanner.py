"""Filesystem scanning for project-guard."""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
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
        if not line or line.startswith(("#", "-")):
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


def _pom_names(path: Path) -> list[str]:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ET.ParseError):
        return []
    names: list[str] = []
    for dependency in root.iter():
        if dependency.tag.rsplit("}", 1)[-1] != "dependency":
            continue
        values = {
            child.tag.rsplit("}", 1)[-1]: (child.text or "").strip()
            for child in dependency
        }
        group = values.get("groupId")
        artifact = values.get("artifactId")
        if group and artifact:
            names.append(f"{group}:{artifact}")
    return names


def _gradle_names(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    pattern = re.compile(
        r"\b(?:implementation|api|testImplementation|runtimeOnly|compileOnly)"
        r"\s*(?:\(\s*)?[\"']([^\"']+)[\"']\s*\)?"
    )
    return [match.group(1) for match in pattern.finditer(source)]


def _go_mod_names(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    names: list[str] = []
    in_require = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("require ("):
            in_require = True
            continue
        if in_require and line == ")":
            in_require = False
            continue
        if line.startswith("require "):
            line = line[len("require "):].strip()
        if in_require or raw.startswith("require "):
            parts = line.split()
            if parts and not parts[0].startswith("//"):
                names.append(parts[0])
    return names


def _cargo_names(path: Path) -> list[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    names: list[str] = []
    for section in ("dependencies", "dev-dependencies"):
        values = data.get(section, {})
        if isinstance(values, dict):
            names.extend(str(name) for name in values)
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
    pom = root / "pom.xml"
    if pom.is_file():
        add("pom.xml", _pom_names(pom))
    for name in ("build.gradle", "build.gradle.kts"):
        gradle = root / name
        if gradle.is_file():
            add(name, _gradle_names(gradle))
    go_mod = root / "go.mod"
    if go_mod.is_file():
        add("go.mod", _go_mod_names(go_mod))
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        add("Cargo.toml", _cargo_names(cargo))
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
        python_file_count=sum(
            1 for f in files if Path(f.path).suffix.lower() == ".py"
        ),
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
