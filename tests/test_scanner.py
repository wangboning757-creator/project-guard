from pathlib import Path

from project_guard.scanner import scan_project


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "x = 1\n" * 60, encoding="utf-8"
    )
    (tmp_path / "src" / "utils.py").write_text(
        "y = 2\n" * 30, encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(
        "requests==2.31\nflask>=2.0\n# comment\n\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = [\n'
        '    "typer>=0.12",\n    "pydantic>=2",\n]\n',
        encoding="utf-8",
    )
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "junk.py").write_text("x\n", encoding="utf-8")
    return tmp_path


def test_scan_counts_files_and_lines(tmp_path):
    scan = scan_project(_make_project(tmp_path))
    assert scan.file_count == 5
    assert scan.python_file_count == 2
    assert scan.total_lines == 101
    assert scan.largest_file.path == "src/app.py"
    assert scan.largest_file.lines == 60
    assert [d.path for d in scan.top_dirs] == ["src"]
    assert scan.max_depth == 2


def test_scan_detects_dependencies(tmp_path):
    scan = scan_project(_make_project(tmp_path))
    assert scan.dependency_total == 4
    sources = {d.source: d.names for d in scan.dependencies}
    assert sources["requirements.txt"] == ["requests==2.31", "flask>=2.0"]
    assert sources["pyproject.toml"] == ["typer>=0.12", "pydantic>=2"]


def test_scan_detects_large_file(tmp_path):
    (tmp_path / "big.py").write_text("z = 0\n" * 600, encoding="utf-8")
    scan = scan_project(tmp_path)
    assert [f.path for f in scan.large_files] == ["big.py"]


def test_scan_size_checks_ignore_non_source_files(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "huge.py").write_text("x = 1\n" * 900, encoding="utf-8")
    (tmp_path / "fixture.json").write_text("{}\n" * 900, encoding="utf-8")
    (tmp_path / "image.png").write_text("x\n" * 900, encoding="utf-8")
    (tmp_path / "README.md").write_text("# doc\n" * 900, encoding="utf-8")
    scan = scan_project(tmp_path)
    assert scan.largest_file.path == "huge.py"
    assert [f.path for f in scan.large_files] == ["huge.py"]
