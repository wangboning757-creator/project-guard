"""Central thresholds for project-guard checks."""

from __future__ import annotations

# Filesystem scanning
IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", "dist", "build", "target", ".gradle", ".idea", ".vscode",
}
LARGE_FILE_LINES = 500        # files above this are "oversized"
VERY_LARGE_FILE_LINES = 800   # files above this are "giant"
SOURCE_EXTENSIONS = {
    ".py", ".java", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".go", ".rs", ".html", ".htm",
}   # lightweight source files used for size/ranking checks
MAX_TOP_DIRS = 8
MAX_DEPTH = 6

# Dependencies
DEPENDENCY_SOFT_LIMIT = 15

# Diff review
DIFF_LARGE_ADDITIONS = 400     # total additions considered a large diff
DIFF_HUGE_ADDITIONS = 1000     # total additions considered a very large diff
DIFF_LARGE_FILE_ADDED = 300    # additions in a single file considered large
DIFF_MANY_MODULES = 5          # more changed Python modules than this is a flag
DEPENDENCY_FILES = {
    "requirements.txt", "requirements-dev.txt", "pyproject.toml",
    "poetry.lock", "Pipfile", "Pipfile.lock", "uv.lock",
    "package.json", "package-lock.json", "setup.py", "pom.xml",
    "build.gradle", "build.gradle.kts", "go.mod", "Cargo.toml",
}
