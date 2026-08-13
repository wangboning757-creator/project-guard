"""Pydantic models shared by project-guard commands."""

from __future__ import annotations

from pydantic import BaseModel

from .config import LARGE_FILE_LINES


class FileInfo(BaseModel):
    path: str
    lines: int


class DirSummary(BaseModel):
    path: str
    file_count: int


class DependencySummary(BaseModel):
    source: str
    count: int
    names: list[str] = []


class ScanResult(BaseModel):
    root: str
    file_count: int
    python_file_count: int
    total_lines: int
    max_depth: int
    files: list[FileInfo] = []
    top_dirs: list[DirSummary] = []
    dependencies: list[DependencySummary] = []

    @property
    def dependency_total(self) -> int:
        return sum(d.count for d in self.dependencies)

    @property
    def python_files(self) -> list[FileInfo]:
        return [f for f in self.files if f.path.endswith(".py")]

    @property
    def largest_file(self) -> FileInfo | None:
        return self.files[0] if self.files else None

    @property
    def large_files(self) -> list[FileInfo]:
        return [f for f in self.files if f.lines >= LARGE_FILE_LINES]


class PlanMatch(BaseModel):
    path: str
    keywords: list[str] = []
    hits: int = 0
    lines: int = 0


class PlanResult(BaseModel):
    request: str
    keywords: list[str] = []
    matches: list[PlanMatch] = []
    duplication_risk: bool = False
    suggestion: str = ""


class ReviewResult(BaseModel):
    changed_files: int = 0
    added_files: int = 0
    deleted_files: int = 0
    total_added: int = 0
    total_deleted: int = 0
    dependency_changed: bool = False
    many_modules_changed: bool = False
    large_file_additions: list[str] = []
    changed_python_files: list[str] = []
    duplicated_modules: list[str] = []
    oversized_changed_files: list[str] = []
    risk: str = "LOW"
    reasons: list[str] = []


class ScoreDeduction(BaseModel):
    rule: str
    points: int
    reason: str


class ScoreResult(BaseModel):
    score: int
    deductions: list[ScoreDeduction] = []
