"""Pydantic models shared by project-guard commands."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from .config import LARGE_FILE_LINES, SOURCE_EXTENSIONS


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
        return [
            f for f in self.files if Path(f.path).suffix in SOURCE_EXTENSIONS
        ]

    @property
    def largest_file(self) -> FileInfo | None:
        return self.python_files[0] if self.python_files else None

    @property
    def large_files(self) -> list[FileInfo]:
        return [
            f for f in self.python_files if f.lines >= LARGE_FILE_LINES
        ]


class PlanMatch(BaseModel):
    path: str
    keywords: list[str] = []
    hits: int = 0
    symbol_hits: int = 0
    lines: int = 0


class PlanSnapshot(BaseModel):
    version: int = 1
    goal: str
    recommended_scope: list[str]
    possible_scope: list[str]
    avoid_modifying: list[str]
    new_dependency: str
    new_abstraction: str
    refactor: str
    existing_capability_files: list[str] = []


class PlanResult(BaseModel):
    request: str
    keywords: list[str] = []
    matches: list[PlanMatch] = []
    duplication_risk: bool = False
    suggestion: str = ""
    guardrail: str = ""
    snapshot: PlanSnapshot | None = None
    contract: EngineeringContract | None = None


class ReviewResult(BaseModel):
    changed_files: int = 0
    added_files: int = 0
    deleted_files: int = 0
    total_added: int = 0
    total_deleted: int = 0
    changed_paths: list[str] = []
    added_paths: list[str] = []
    dependency_changed: bool = False
    many_modules_changed: bool = False
    large_file_additions: list[str] = []
    changed_python_files: list[str] = []
    duplicated_modules: list[str] = []
    oversized_changed_files: list[str] = []
    risk: str = "LOW"
    reasons: list[str] = []


class PlanCompliance(BaseModel):
    status: str = "PASS"
    goal: str = ""
    allowed_scope: list[str] = []
    actual_changes: list[str] = []
    violations: list[str] = []
    reuse_warnings: list[str] = []
    risk: str = "LOW"


class ComplexityBudget(BaseModel):
    """Preferred structural limits used only as a signal baseline.

    Not an implementation optimality metric. A budget is exceeded to flag
    unexpected structural expansion, never to declare an implementation
    wrong.
    """

    preferred_new_production_files: int = 0
    preferred_new_abstractions: int = 0
    preferred_new_dependencies: int = 0
    preferred_max_touched_production_files: int = 3


class EngineeringContract(BaseModel):
    """Guard-side contract produced by Project Guard.

    EngineeringContract contains repository-specific evidence and
    governance constraints produced by Project Guard.

    It is not a complete semantic interpretation of the user's request.
    The Coding Agent is responsible for producing or confirming
    task-level requirements and assumptions.
    """

    version: int = 1
    original_request: str
    explicit_requirements: list[str] = []
    # Engineering governance constraints, NOT inferred user requirements.
    inferred_requirements: list[str] = []
    assumptions: list[str] = []
    unresolved_questions: list[str] = []
    repository_facts: list[str] = []
    recommended_scope: list[str] = []
    possible_scope: list[str] = []
    avoid_modifying: list[str] = []
    existing_capability_files: list[str] = []
    new_dependency: str = "not justified"
    new_abstraction: str = "not justified"
    refactor: str = "not justified"
    complexity_budget: ComplexityBudget = ComplexityBudget()
    testing_policy: str = ""


class ContractAmendment(BaseModel):
    """A requested scope change against an immutable EngineeringContract."""

    version: int = 1
    requested_files: list[str] = []
    reason: str = ""
    safe_in_scope_alternative_exists: bool = False
    status: str = "pending"  # pending / approved / rejected


class RemediationConstraint(BaseModel):
    finding_type: str
    severity: str
    constraints: list[str] = []
    evidence: list[str] = []
    requires_scope_amendment: list[str] = []


class ComplexitySignal(BaseModel):
    level: str = "LOW"
    touched_production_files: int = 0
    new_production_files: int = 0
    new_top_level_classes: int = 0
    new_top_level_functions: int = 0
    dependency_changed: bool = False


class ScoreDeduction(BaseModel):
    rule: str
    points: int
    reason: str


class ScoreResult(BaseModel):
    score: int
    deductions: list[ScoreDeduction] = []
