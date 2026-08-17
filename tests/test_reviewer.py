import json
import subprocess
from pathlib import Path

import pytest

from project_guard.models import (
    ComplexityBudget,
    ContractAmendment,
    EngineeringContract,
    PlanCompliance,
    PlanSnapshot,
    TaskContract,
)
from project_guard.reviewer import (
    ContractError,
    NotAGitRepoError,
    PlanSnapshotError,
    TaskContractError,
    analyze_diff,
    approved_amendment_files,
    build_remediation_constraints,
    check_complexity,
    check_plan_compliance,
    check_requirement_fidelity,
    check_reuse_warnings,
    contract_to_snapshot,
    load_engineering_contract,
    load_plan_snapshot,
    load_task_contract,
)

DOMAIN_GOAL = (
    "Add an option to exclude one or more domains from research search "
    "results"
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    return tmp_path


def test_review_small_change_is_low(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    result = analyze_diff(repo)
    assert result.changed_files == 1
    assert result.total_added == 1
    assert result.risk == "LOW"


def test_review_large_diff_is_high(repo):
    (repo / "new_module.py").write_text(
        "x = 1\n" * 1100, encoding="utf-8"
    )
    result = analyze_diff(repo)
    assert result.added_files == 1
    assert result.risk == "HIGH"
    assert result.large_file_additions


def test_review_large_existing_file_small_change_stays_low(repo):
    (repo / "large.py").write_text("x = 1\n" * 900, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add large file")
    (repo / "large.py").write_text(
        "x = 1\n" * 900 + "x = 2\n" * 5, encoding="utf-8"
    )
    result = analyze_diff(repo)
    assert result.risk == "LOW"
    assert result.oversized_changed_files == ["large.py"]
    assert not any("oversized" in r for r in result.reasons)


def test_review_dependency_change_is_medium(repo):
    (repo / "requirements.txt").write_text(
        "requests==2.31\n", encoding="utf-8"
    )
    result = analyze_diff(repo)
    assert result.dependency_changed
    assert result.risk == "MEDIUM"


def test_review_not_git(tmp_path):
    with pytest.raises(NotAGitRepoError):
        analyze_diff(tmp_path)


def test_analyze_diff_excludes_plan_file(repo):
    (repo / ".project-guard-plan.json").write_text(
        '{"version": 1}', encoding="utf-8"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_new.py").write_text(
        "def t():\n    pass\n", encoding="utf-8"
    )
    (repo / "pkg.py").write_text("x = 1\n", encoding="utf-8")
    result = analyze_diff(
        repo, exclude_paths={repo / ".project-guard-plan.json"}
    )
    assert ".project-guard-plan.json" not in result.changed_paths
    assert "tests/test_new.py" in result.changed_paths
    assert "pkg.py" in result.changed_paths
    assert result.added_files == 2


def test_plan_compliance_ignores_plan_snapshot_file(repo):
    plan = PlanSnapshot(
        goal="x",
        recommended_scope=["pkg.py"],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    (repo / ".project-guard-plan.json").write_text(
        '{"version": 1}', encoding="utf-8"
    )
    (repo / "pkg.py").write_text("x = 1\n", encoding="utf-8")
    result = analyze_diff(
        repo, exclude_paths={repo / ".project-guard-plan.json"}
    )
    compliance = check_plan_compliance(plan, result)
    assert compliance.status == "PASS"


def test_plan_snapshot_json_round_trip(tmp_path):
    snap = PlanSnapshot(
        goal="Add a new response decoder",
        recommended_scope=["pkg/decoder.py"],
        possible_scope=["pkg/client.py"],
        avoid_modifying=["pkg/storage.py"],
        new_dependency="not justified",
        new_abstraction="reuse existing structure",
        refactor="not justified",
    )
    path = tmp_path / "plan.json"
    path.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
    assert load_plan_snapshot(path) == snap


def test_load_plan_snapshot_errors(tmp_path):
    with pytest.raises(PlanSnapshotError):
        load_plan_snapshot(tmp_path / "missing.json")

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(PlanSnapshotError):
        load_plan_snapshot(bad)

    version = tmp_path / "version.json"
    version.write_text('{"version": 2}', encoding="utf-8")
    with pytest.raises(PlanSnapshotError):
        load_plan_snapshot(version)

    missing_field = tmp_path / "missing_field.json"
    missing_field.write_text('{"version": 1, "goal": "x"}', encoding="utf-8")
    with pytest.raises(PlanSnapshotError):
        load_plan_snapshot(missing_field)


def test_plan_compliance_pass(repo):
    plan = PlanSnapshot(
        goal="Add a new response decoder",
        recommended_scope=["app.py"],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_app.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8"
    )
    result = analyze_diff(repo)
    compliance = check_plan_compliance(plan, result)
    assert compliance.status == "PASS"
    assert compliance.risk == "LOW"
    assert compliance.violations == []


def test_plan_compliance_unplanned_production_files(repo):
    plan = PlanSnapshot(
        goal="x",
        recommended_scope=["app.py"],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "models.py").write_text("x = 1\n", encoding="utf-8")
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "WARNING"
    assert compliance.risk == "MEDIUM"
    assert any(
        "Unplanned production file: models.py" in v
        for v in compliance.violations
    )

    (repo / "transport.py").write_text("y = 2\n", encoding="utf-8")
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "VIOLATION"
    assert compliance.risk == "HIGH"


def test_plan_compliance_avoided_file(repo):
    plan = PlanSnapshot(
        goal="x",
        recommended_scope=["app.py"],
        possible_scope=[],
        avoid_modifying=["models.py"],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    (repo / "models.py").write_text("x = 1\n", encoding="utf-8")
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "VIOLATION"
    assert compliance.risk == "HIGH"
    assert any(
        "Modified explicitly avoided file: models.py" in v
        for v in compliance.violations
    )


def test_plan_compliance_dependency_conflict(repo):
    plan = PlanSnapshot(
        goal="x",
        recommended_scope=[],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    (repo / "requirements.txt").write_text(
        "requests==2.31\n", encoding="utf-8"
    )
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "WARNING"
    assert compliance.risk == "MEDIUM"
    assert any(
        "Dependency file changed" in v for v in compliance.violations
    )


def test_plan_compliance_refactor_signal(repo):
    plan = PlanSnapshot(
        goal="x",
        recommended_scope=[],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        (repo / name).write_text(f"# {name}\n", encoding="utf-8")
    compliance = check_plan_compliance(plan, analyze_diff(repo))
    assert compliance.status == "VIOLATION"
    assert compliance.risk == "HIGH"
    assert any(
        "Possible unplanned refactor" in v for v in compliance.violations
    )


def test_review_excludes_plan_and_instructions_files(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "README.md").write_text(
        "ok\nchanged\n", encoding="utf-8"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_app.py").write_text(
        "def t():\n    pass\n", encoding="utf-8"
    )
    (repo / ".project-guard-plan.json").write_text(
        '{"version": 1}', encoding="utf-8"
    )
    (repo / ".project-guard-instructions.md").write_text(
        "# instructions\n", encoding="utf-8"
    )
    result = analyze_diff(
        repo,
        exclude_paths={
            repo / ".project-guard-plan.json",
            repo / ".project-guard-instructions.md",
        },
    )
    assert ".project-guard-plan.json" not in result.changed_paths
    assert ".project-guard-instructions.md" not in result.changed_paths
    assert "app.py" in result.changed_paths
    assert "tests/test_app.py" in result.changed_paths
    assert "README.md" in result.changed_paths
    assert result.changed_files == 3


def test_review_does_not_implicitly_ignore_instructions(repo):
    (repo / ".project-guard-instructions.md").write_text(
        "# instructions\n", encoding="utf-8"
    )
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    result = analyze_diff(repo)
    assert ".project-guard-instructions.md" in result.changed_paths


def test_review_other_markdown_still_counted(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / ".project-guard-instructions.md").write_text(
        "# instructions\n", encoding="utf-8"
    )
    (repo / "notes.md").write_text("# notes\n", encoding="utf-8")
    result = analyze_diff(
        repo, exclude_paths={repo / ".project-guard-instructions.md"}
    )
    assert ".project-guard-instructions.md" not in result.changed_paths
    assert "notes.md" in result.changed_paths


def _add_domain_capability(repo):
    (repo / "search").mkdir()
    (repo / "search" / "tavily.py").write_text(
        "class TavilySearchProvider:\n"
        "    def __init__(self, exclude_domains=()):\n"
        "        self.exclude_domains = exclude_domains\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "capability")


def _domain_snapshot(**overrides) -> PlanSnapshot:
    base = dict(
        goal=DOMAIN_GOAL,
        recommended_scope=["app.py"],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
        existing_capability_files=["search/tavily.py"],
    )
    base.update(overrides)
    return PlanSnapshot(**base)


def test_reuse_warns_on_overlapping_new_class(repo):
    _add_domain_capability(repo)
    (repo / "app.py").write_text(
        "print('hi')\n"
        "class ExcludedDomainSearchProvider:\n"
        "    pass\n",
        encoding="utf-8",
    )
    result = analyze_diff(repo)
    warnings = check_reuse_warnings(repo, _domain_snapshot(), result)
    assert any("possible duplicate implementation" in w for w in warnings)
    assert "ExcludedDomainSearchProvider" in " ".join(warnings)
    assert "search/tavily.py" in " ".join(warnings)


def test_reuse_no_warning_on_wiring(repo):
    _add_domain_capability(repo)
    (repo / "app.py").write_text(
        "print('hi')\n"
        "provider = TavilySearchProvider(exclude_domains=())\n",
        encoding="utf-8",
    )
    result = analyze_diff(repo)
    assert check_reuse_warnings(repo, _domain_snapshot(), result) == []


def test_reuse_no_warning_on_unrelated_symbol(repo):
    _add_domain_capability(repo)
    (repo / "app.py").write_text(
        "print('hi')\n"
        "def validate_cli_path(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    result = analyze_diff(repo)
    assert check_reuse_warnings(repo, _domain_snapshot(), result) == []


def test_reuse_no_warning_when_capability_file_modified(repo):
    _add_domain_capability(repo)
    (repo / "app.py").write_text(
        "print('hi')\n"
        "class ExcludedDomainSearchProvider:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (repo / "search" / "tavily.py").write_text(
        "class TavilySearchProvider:\n"
        "    def __init__(self, exclude_domains=()):\n"
        "        self.exclude_domains = exclude_domains\n"
        "        self.include_domains = ()\n",
        encoding="utf-8",
    )
    result = analyze_diff(repo)
    assert check_reuse_warnings(repo, _domain_snapshot(), result) == []


def test_reuse_no_warning_on_provider_expansion_goal(repo):
    (repo / "providers.py").write_text(
        "class ProviderVendor:\n    pass\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "providers")
    (repo / "app.py").write_text(
        "print('hi')\n"
        "class NewProviderVendor:\n"
        "    pass\n",
        encoding="utf-8",
    )
    snapshot = _domain_snapshot(
        goal="Add support for another provider vendor",
        existing_capability_files=["providers.py"],
    )
    result = analyze_diff(repo)
    assert check_reuse_warnings(repo, snapshot, result) == []


def test_load_plan_snapshot_without_capability_field(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(
        '{"version": 1, "goal": "x", "recommended_scope": [], '
        '"possible_scope": [], "avoid_modifying": [], '
        '"new_dependency": "not justified", '
        '"new_abstraction": "not justified", "refactor": "not justified"}',
        encoding="utf-8",
    )
    snap = load_plan_snapshot(path)
    assert snap.existing_capability_files == []


def test_load_engineering_contract_errors(tmp_path):
    with pytest.raises(ContractError):
        load_engineering_contract(tmp_path / "missing.json")

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ContractError):
        load_engineering_contract(bad)

    version = tmp_path / "version.json"
    version.write_text('{"version": 2}', encoding="utf-8")
    with pytest.raises(ContractError):
        load_engineering_contract(version)

    missing = tmp_path / "missing_field.json"
    missing.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(ContractError):
        load_engineering_contract(missing)


def test_engineering_contract_json_round_trip(tmp_path):
    contract = EngineeringContract(
        original_request="Add a CLI option",
        explicit_requirements=["Add a CLI option"],
        recommended_scope=["app.py"],
        possible_scope=["workflow.py"],
        avoid_modifying=["writer.py"],
        existing_capability_files=["search/tavily.py"],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    path = tmp_path / "contract.json"
    path.write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    loaded = load_engineering_contract(path)
    assert loaded == contract
    snapshot = contract_to_snapshot(loaded)
    assert snapshot.recommended_scope == ["app.py"]
    assert snapshot.existing_capability_files == ["search/tavily.py"]


def _contract_for_repo(**overrides) -> EngineeringContract:
    base = dict(
        original_request="Add a CLI option",
        explicit_requirements=["Add a CLI option"],
        inferred_requirements=[],
        assumptions=[],
        unresolved_questions=[],
        repository_facts=[],
        recommended_scope=["app.py"],
        possible_scope=[],
        avoid_modifying=[],
        existing_capability_files=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
        complexity_budget=ComplexityBudget(),
        testing_policy="",
    )
    base.update(overrides)
    return EngineeringContract(**base)


def test_complexity_within_budget_stays_low(repo):
    (repo / "workflow.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add workflow")
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "workflow.py").write_text("x = 2\n", encoding="utf-8")
    result = analyze_diff(repo)
    signal = check_complexity(repo, _contract_for_repo(), result)
    assert signal.level == "LOW"
    assert signal.touched_production_files == 2


def test_complexity_new_classes_is_medium(repo):
    (repo / "app.py").write_text(
        "print('hi')\n"
        "class Alpha:\n"
        "    pass\n"
        "class Beta:\n"
        "    pass\n",
        encoding="utf-8",
    )
    result = analyze_diff(repo)
    signal = check_complexity(repo, _contract_for_repo(), result)
    assert signal.level == "MEDIUM"
    assert signal.new_top_level_classes == 2


def test_complexity_single_new_file_is_low(repo):
    (repo / "extra.py").write_text("x = 1\n", encoding="utf-8")
    result = analyze_diff(repo)
    signal = check_complexity(repo, _contract_for_repo(), result)
    assert signal.level == "LOW"
    assert signal.new_production_files == 1


def test_complexity_combined_signals_is_medium(repo):
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        (repo / name).write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "files")
    (repo / "app.py").write_text(
        "print('hi')\n"
        "class A:\n    pass\n"
        "class B:\n    pass\n"
        "class C:\n    pass\n",
        encoding="utf-8",
    )
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        (repo / name).write_text("x = 2\n", encoding="utf-8")
    (repo / "requirements.txt").write_text(
        "requests==2.31\n", encoding="utf-8"
    )
    result = analyze_diff(repo)
    signal = check_complexity(repo, _contract_for_repo(), result)
    assert signal.level == "MEDIUM"
    assert signal.touched_production_files == 6
    assert signal.new_top_level_classes == 3
    assert signal.dependency_changed


def test_requirement_fidelity_no_conflict(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    result = analyze_diff(repo)
    assert (
        check_requirement_fidelity(_contract_for_repo(), result)
        == "STRUCTURAL CHECK ONLY"
    )


def test_requirement_fidelity_unresolved_questions_do_not_force_conflict(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    contract = _contract_for_repo(
        unresolved_questions=["Should this apply to the web interface?"]
    )
    result = analyze_diff(repo)
    assert (
        check_requirement_fidelity(contract, result)
        == "STRUCTURAL CHECK ONLY"
    )


def test_requirement_fidelity_unrelated_changes(repo):
    (repo / "other.py").write_text("x = 1\n", encoding="utf-8")
    result = analyze_diff(repo)
    assert (
        check_requirement_fidelity(_contract_for_repo(), result)
        == "NEEDS HUMAN CONFIRMATION"
    )


def test_remediation_constraints_from_violations_and_warnings():
    compliance = PlanCompliance(
        status="VIOLATION",
        risk="HIGH",
        violations=[
            "Modified explicitly avoided file: models.py",
            "Unplanned production file: transport.py",
        ],
    )
    constraints = build_remediation_constraints(
        compliance,
        [
            "possible duplicate implementation: new `X` in cli.py "
            "overlaps existing capability in search/tavily.py"
        ],
    )
    assert any(
        c.finding_type == "duplicate_implementation"
        for c in constraints
    )
    avoid = [
        c
        for c in constraints
        if "models.py" in c.requires_scope_amendment
    ]
    assert avoid and avoid[0].severity == "high"
    unplanned = [
        c
        for c in constraints
        if "transport.py" in c.requires_scope_amendment
    ]
    assert unplanned


def _plain_plan(**overrides) -> PlanSnapshot:
    base = dict(
        goal="x",
        recommended_scope=["app.py"],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    base.update(overrides)
    return PlanSnapshot(**base)


def _amendment(status: str = "approved") -> ContractAmendment:
    return ContractAmendment(
        requested_files=["workflow.py"],
        reason="workflow owns stop decision",
        safe_in_scope_alternative_exists=False,
        status=status,
    )


def test_review_approved_scope_amendment_allows_file(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "workflow.py").write_text("x = 1\n", encoding="utf-8")
    result = analyze_diff(repo)
    compliance = check_plan_compliance(
        _plain_plan(), result, amendments=[_amendment()]
    )
    assert compliance.status == "PASS"
    assert "workflow.py" in compliance.approved_scope_amendments
    assert "workflow.py" in compliance.effective_allowed_scope
    assert not any(
        "Unplanned production file: workflow.py" in v
        for v in compliance.violations
    )
    constraints = build_remediation_constraints(compliance, [])
    assert not any(
        c.finding_type == "scope_violation" for c in constraints
    )


def test_review_pending_scope_amendment_does_not_expand_scope(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "workflow.py").write_text("x = 1\n", encoding="utf-8")
    result = analyze_diff(repo)
    compliance = check_plan_compliance(
        _plain_plan(), result, amendments=[_amendment(status="pending")]
    )
    assert compliance.status == "WARNING"
    assert any(
        "Unplanned production file: workflow.py" in v
        for v in compliance.violations
    )
    constraints = build_remediation_constraints(compliance, [])
    assert any(
        c.finding_type == "scope_violation" for c in constraints
    )


def test_review_rejected_scope_amendment_does_not_expand_scope(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "workflow.py").write_text("x = 1\n", encoding="utf-8")
    result = analyze_diff(repo)
    compliance = check_plan_compliance(
        _plain_plan(), result, amendments=[_amendment(status="rejected")]
    )
    assert compliance.status == "WARNING"
    assert any(
        "Unplanned production file: workflow.py" in v
        for v in compliance.violations
    )


def test_review_amendment_overrides_avoid(repo):
    (repo / "workflow.py").write_text("x = 1\n", encoding="utf-8")
    result = analyze_diff(repo)
    compliance = check_plan_compliance(
        _plain_plan(avoid_modifying=["workflow.py"]),
        result,
        amendments=[_amendment()],
    )
    assert compliance.status == "PASS"
    assert "workflow.py" in compliance.avoid_overridden
    assert not any(
        "Modified explicitly avoided file" in v
        for v in compliance.violations
    )


def test_task_contract_planned_files_do_not_expand_scope(repo):
    (repo / "app.py").write_text(
        "print('hi')\nprint('bye')\n", encoding="utf-8"
    )
    (repo / "workflow.py").write_text("x = 1\n", encoding="utf-8")
    path = repo / "task.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "original_request": "x",
                "planned_production_files": ["workflow.py"],
                "scope_amendments": [],
            }
        ),
        encoding="utf-8",
    )
    task = load_task_contract(path)
    assert approved_amendment_files(task) == []
    result = analyze_diff(repo)
    compliance = check_plan_compliance(
        _plain_plan(), result, amendments=task.scope_amendments
    )
    assert compliance.status == "WARNING"
    assert any(
        "Unplanned production file: workflow.py" in v
        for v in compliance.violations
    )


def test_task_contract_amendments_alias_preserves_canonical_field(tmp_path):
    amendment = {
        "version": 1,
        "requested_files": ["workflow.py"],
        "reason": "User approved the workflow scope.",
        "safe_in_scope_alternative_exists": False,
        "status": "approved",
    }
    canonical_path = tmp_path / "canonical.json"
    canonical_path.write_text(
        json.dumps(
            {
                "version": 1,
                "original_request": "x",
                "scope_amendments": [amendment],
            }
        ),
        encoding="utf-8",
    )
    alias_path = tmp_path / "alias.json"
    alias_path.write_text(
        json.dumps(
            {
                "version": 1,
                "original_request": "x",
                "amendments": [amendment],
            }
        ),
        encoding="utf-8",
    )

    canonical = load_task_contract(canonical_path)
    alias = load_task_contract(alias_path)

    assert canonical.scope_amendments == alias.scope_amendments
    assert alias.model_dump()["scope_amendments"] == [amendment]
    assert "amendments" not in alias.model_dump()


def test_load_task_contract_errors(tmp_path):
    with pytest.raises(TaskContractError):
        load_task_contract(tmp_path / "missing.json")

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(TaskContractError):
        load_task_contract(bad)

    version = tmp_path / "version.json"
    version.write_text('{"version": 2}', encoding="utf-8")
    with pytest.raises(TaskContractError):
        load_task_contract(version)

    missing = tmp_path / "missing_field.json"
    missing.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(TaskContractError):
        load_task_contract(missing)


def test_task_contract_extra_fields_ignored(tmp_path):
    path = tmp_path / "task.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "original_request": "x",
                "planned_test_files": ["tests/test_x.py"],
                "ambiguity_check": {"ambiguous": False},
                "scope_amendments": [],
            }
        ),
        encoding="utf-8",
    )
    task = load_task_contract(path)
    assert task.original_request == "x"
    assert isinstance(task, TaskContract)
