"""Phase 6A end-to-end evaluations.

Each eval freezes a behavior that was verified on a real repository into a
minimal fixture repo plus a behavioral ``expected.json``, and runs the real
planner/reviewer public API against it.

Plan evals assert only behavioral expectations (scope membership, avoid
lists, dependency justification, duplication risk) - never the full
markdown output and never a complete file ordering, so minor wording or
ranking changes do not break the evals.

Review evals copy a fixture repo into ``tmp_path``, build a real git repo
there, generate the plan snapshot with the real planner, then make the
changes and run the real diff review + plan compliance check. No git
commands are mocked.
"""

import json
import shutil
import subprocess
from pathlib import Path

from project_guard.instructions import format_instructions, skill_template_text
from project_guard.models import EngineeringContract
from project_guard.planner import analyze_plan
from project_guard.reviewer import (
    analyze_diff,
    build_remediation_constraints,
    check_plan_compliance,
    check_reuse_warnings,
    contract_to_snapshot,
    merge_risk,
)

EVALS_DIR = Path(__file__).parent / "evals"
TXT_EVAL_DIR = EVALS_DIR / "txt_export"
MAX_SOURCES_EVAL_DIR = EVALS_DIR / "max_sources"
DOMAIN_EXCLUSION_EVAL_DIR = EVALS_DIR / "domain_exclusion"


def _load_expected(eval_dir: Path) -> dict:
    return json.loads((eval_dir / "expected.json").read_text(encoding="utf-8"))


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_git_repo(fixture: Path, tmp_path: Path) -> Path:
    """Copy a fixture repo into tmp_path and commit it as a real git repo."""
    repo = tmp_path / "repo"
    shutil.copytree(
        fixture,
        repo,
        ignore=shutil.ignore_patterns("__pycache__", ".git", "*.pyc"),
    )
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "eval@example.com")
    _git(repo, "config", "user.name", "Project Guard Eval")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def _assert_plan_expectations(result, snap, expected: dict) -> None:
    for key in (
        "recommended_scope_contains",
        "recommended_scope_not_contains",
        "possible_scope_contains",
        "possible_scope_not_contains",
    ):
        if key.endswith("_not_contains"):
            scope, op = key[: -len("_not_contains")], "not_contains"
        else:
            scope, op = key[: -len("_contains")], "contains"
        actual = (
            snap.recommended_scope
            if scope == "recommended_scope"
            else snap.possible_scope
        )
        for path in expected.get(key, []):
            if op == "contains":
                assert path in actual, (
                    f"expected {path!r} in {scope}_scope, got {actual!r}"
                )
            else:
                assert path not in actual, (
                    f"expected {path!r} not in {scope}_scope, got {actual!r}"
                )
    for path in expected.get("avoid_contains", []):
        assert path in snap.avoid_modifying, (
            f"expected {path!r} in avoid_modifying, got "
            f"{snap.avoid_modifying!r}"
        )
    for path in expected.get("avoid_not_contains", []):
        assert path not in snap.avoid_modifying, (
            f"expected {path!r} not in avoid_modifying, got "
            f"{snap.avoid_modifying!r}"
        )
    if "new_dependency" in expected:
        assert snap.new_dependency == expected["new_dependency"]
    if "duplication_risk" in expected:
        assert result.duplication_risk == expected["duplication_risk"]
    for needle in expected.get("guardrail_not_contains", []):
        assert needle not in result.guardrail, (
            f"expected guardrail not to contain {needle!r}"
        )
    for needle in expected.get("suggestion_not_contains", []):
        assert needle not in result.suggestion.lower(), (
            f"expected suggestion not to contain {needle!r}: "
            f"{result.suggestion!r}"
        )


# ---------------------------------------------------------------- plan evals


def test_eval_plan_txt_export():
    """Eval 1: plain-text .txt report export keeps writer.py as owner.

    Guards the historical bug where usage/integration sites (workflow,
    cli, web tasks) displaced the capability owner in the recommended
    scope, or were listed as files to avoid.
    """
    expected = _load_expected(TXT_EVAL_DIR)
    result = analyze_plan(TXT_EVAL_DIR / "repo", expected["goal"])
    snap = result.snapshot
    assert snap is not None
    _assert_plan_expectations(result, snap, expected)


def test_eval_plan_max_sources():
    """Eval 2: max-sources CLI option does not get taken over by the
    existing search provider abstraction.

    Guards the historical bug where a parameter change with a keyword
    ("sources") inside a repo that has a provider abstraction was
    re-planned as an abstraction expansion instead of a CLI parameter
    change.
    """
    expected = _load_expected(MAX_SOURCES_EVAL_DIR)
    result = analyze_plan(MAX_SOURCES_EVAL_DIR / "repo", expected["goal"])
    snap = result.snapshot
    assert snap is not None
    _assert_plan_expectations(result, snap, expected)


def test_eval_plan_domain_exclusion():
    """Eval 3: exclude-domains goal keeps cli.py as the recommended owner
    and never lists the direct capability module (tavily.py, which defines
    exclude_domains/include_domains) in avoid_modifying.

    Guards the historical bug where a usage-only avoid heuristic banned a
    module with direct capability evidence for the current goal.
    """
    expected = _load_expected(DOMAIN_EXCLUSION_EVAL_DIR)
    result = analyze_plan(
        DOMAIN_EXCLUSION_EVAL_DIR / "repo", expected["goal"]
    )
    snap = result.snapshot
    assert snap is not None
    _assert_plan_expectations(result, snap, expected)
    assert snap.new_abstraction == "not justified"
    assert snap.refactor == "not justified"


def test_eval_plan_reuse_tavily_capability():
    """Eval: reuse-existing-capability goal surfaces the factory wiring
    point instead of the capability owner or config-only modules."""
    goal = (
        "Reuse the existing Tavily exclude_domains capability for the CLI "
        "domain-exclusion option instead of client-side filtering"
    )
    result = analyze_plan(DOMAIN_EXCLUSION_EVAL_DIR / "repo", goal)
    snap = result.snapshot
    assert snap is not None
    assert "src/sample_app/cli.py" in snap.recommended_scope
    assert "src/sample_app/factory.py" in snap.possible_scope
    assert "src/sample_app/search/tavily.py" not in snap.avoid_modifying
    assert snap.new_dependency == "not justified"
    assert "provider abstraction" not in result.suggestion.lower()
    assert "new provider module" not in result.guardrail
    assert (
        "Existing capability in src/sample_app/search/tavily.py"
        in result.guardrail
    )


# ---------------------------------------------------------------- review evals


def test_review_case_a_txt_scope_change_passes(tmp_path):
    """Case A: change writer.py + workflow.py + cli.py (the planned
    scope) in the TXT repo -> Plan Compliance PASS, no unplanned file."""
    repo = _init_git_repo(TXT_EVAL_DIR / "repo", tmp_path)
    expected = _load_expected(TXT_EVAL_DIR)
    snapshot = analyze_plan(repo, expected["goal"]).snapshot
    assert snapshot is not None

    _append(
        repo / "src/sample_app/writer.py",
        "\n\n"
        "def export_txt(path: str, topic: str) -> str:\n"
        '    """Export the report as plain text."""\n'
        '    with open(path, "w", encoding="utf-8") as handle:\n'
        "        handle.write(render_markdown(topic, []))\n"
        "    return path\n",
    )
    _append(
        repo / "src/sample_app/workflow.py",
        "\n\n"
        "def run_with_txt_export(topic: str, path: str) -> str:\n"
        '    """Run the workflow and export a plain-text copy."""\n'
        "    from .writer import export_txt\n\n"
        "    export_txt(path, topic)\n"
        "    return render_markdown(topic, [])\n",
    )
    _append(
        repo / "src/sample_app/cli.py",
        "\n\n"
        "def export_cmd(topic: str) -> None:\n"
        '    """Export the plain-text report from the CLI."""\n'
        '    typer.echo(render_markdown(topic, []))\n',
    )

    compliance = check_plan_compliance(snapshot, analyze_diff(repo))
    assert compliance.status == "PASS"
    assert compliance.risk == "LOW"
    assert not any(
        "Unplanned production file" in v for v in compliance.violations
    ), compliance.violations
    assert sorted(compliance.actual_changes) == [
        "src/sample_app/cli.py",
        "src/sample_app/workflow.py",
        "src/sample_app/writer.py",
    ]


def test_review_case_b_max_sources_cli_only_passes(tmp_path):
    """Case B: change only cli.py in the max-sources repo
    -> Plan Compliance PASS."""
    repo = _init_git_repo(MAX_SOURCES_EVAL_DIR / "repo", tmp_path)
    expected = _load_expected(MAX_SOURCES_EVAL_DIR)
    snapshot = analyze_plan(repo, expected["goal"]).snapshot
    assert snapshot is not None

    _append(
        repo / "src/sample_app/cli.py",
        "\n\n"
        "def set_max_sources(value: int) -> None:\n"
        '    """Update the maximum number of sources for the run."""\n'
        "    _current_limit = value\n",
    )

    compliance = check_plan_compliance(snapshot, analyze_diff(repo))
    assert compliance.status == "PASS"
    assert compliance.risk == "LOW"
    assert compliance.violations == []


def test_review_case_c_avoided_file_is_high_violation(tmp_path):
    """Case C: additionally modify a production file the plan explicitly
    avoids -> VIOLATION with HIGH risk."""
    repo = _init_git_repo(TXT_EVAL_DIR / "repo", tmp_path)
    expected = _load_expected(TXT_EVAL_DIR)
    snapshot = analyze_plan(repo, expected["goal"]).snapshot
    assert snapshot is not None
    assert snapshot.avoid_modifying, (
        "fixture must produce a non-empty avoid list for this case"
    )
    avoided = snapshot.avoid_modifying[0]

    _append(
        repo / avoided,
        "\n\n"
        "def _guardrail_probe() -> None:\n"
        "    pass\n",
    )

    compliance = check_plan_compliance(snapshot, analyze_diff(repo))
    assert compliance.status == "VIOLATION"
    assert compliance.risk == "HIGH"
    assert any(
        f"Modified explicitly avoided file: {avoided}" in v
        for v in compliance.violations
    ), compliance.violations


def test_review_case_d_two_unplanned_production_files(tmp_path):
    """Case D: modify two production files outside the allowed scope and
    not avoided -> VIOLATION with HIGH risk."""
    repo = _init_git_repo(MAX_SOURCES_EVAL_DIR / "repo", tmp_path)
    expected = _load_expected(MAX_SOURCES_EVAL_DIR)
    snapshot = analyze_plan(repo, expected["goal"]).snapshot
    assert snapshot is not None

    allowed = set(snapshot.recommended_scope) | set(snapshot.possible_scope)
    unplanned = [
        "src/sample_app/search/google.py",
        "src/sample_app/search/bing.py",
    ]
    for path in unplanned:
        assert path not in allowed, (
            f"{path!r} must stay outside the planned scope for this case: "
            f"allowed={sorted(allowed)!r}"
        )
        assert path not in snapshot.avoid_modifying, (
            f"{path!r} must not be in avoid_modifying for this case: "
            f"{snapshot.avoid_modifying!r}"
        )

    for path in unplanned:
        _append(
            repo / path,
            "\n\n"
            "def fallback_search() -> None:\n"
            "    pass\n",
        )

    compliance = check_plan_compliance(snapshot, analyze_diff(repo))
    assert compliance.status == "VIOLATION"
    assert compliance.risk == "HIGH"
    unplanned_violations = [
        v
        for v in compliance.violations
        if v.startswith("Unplanned production file")
    ]
    assert len(unplanned_violations) == 2, compliance.violations


def test_review_reuse_duplicate_capability_warns(tmp_path):
    """Domain exclusion: adding a new overlapping top-level class inside
    the allowed scope keeps Plan Compliance PASS but emits a
    reuse-before-build warning and lifts merged risk to MEDIUM."""
    repo = _init_git_repo(DOMAIN_EXCLUSION_EVAL_DIR / "repo", tmp_path)
    expected = _load_expected(DOMAIN_EXCLUSION_EVAL_DIR)
    snapshot = analyze_plan(repo, expected["goal"]).snapshot
    assert snapshot is not None
    assert snapshot.existing_capability_files, (
        "fixture must identify an existing capability file for this case"
    )

    _append(
        repo / "src/sample_app/cli.py",
        "\n\n"
        "class ExcludedDomainSearchProvider:\n"
        "    def __init__(self, exclude_domains: tuple[str, ...] = ()):\n"
        "        self.exclude_domains = exclude_domains\n",
    )

    result = analyze_diff(repo)
    compliance = check_plan_compliance(snapshot, result)
    warnings = check_reuse_warnings(repo, snapshot, result)
    assert compliance.status == "PASS"
    assert any("possible duplicate implementation" in w for w in warnings)
    assert "src/sample_app/search/tavily.py" in " ".join(warnings)
    if warnings:
        compliance.risk = merge_risk(compliance.risk, "MEDIUM")
    assert compliance.risk == "MEDIUM"


def test_review_reuse_wiring_no_warning(tmp_path):
    """Domain exclusion: wiring-only change reusing the existing provider
    produces no reuse warning and keeps PASS / LOW."""
    repo = _init_git_repo(DOMAIN_EXCLUSION_EVAL_DIR / "repo", tmp_path)
    expected = _load_expected(DOMAIN_EXCLUSION_EVAL_DIR)
    snapshot = analyze_plan(repo, expected["goal"]).snapshot
    assert snapshot is not None

    _append(
        repo / "src/sample_app/cli.py",
        "\n\n"
        "def research_with_domains(domains: list[str]) -> dict:\n"
        "    provider = TavilySearchProvider("
        "exclude_domains=tuple(domains))\n"
        "    return provider.search('q')\n",
    )

    result = analyze_diff(repo)
    compliance = check_plan_compliance(snapshot, result)
    assert compliance.status == "PASS"
    assert check_reuse_warnings(repo, snapshot, result) == []


def test_e2e_contract_domain_exclusion():
    """Engineering Contract preserves the original request, keeps explicit
    requirements conservative, and carries planner scope/capability facts."""
    goal = _load_expected(DOMAIN_EXCLUSION_EVAL_DIR)["goal"]
    result = analyze_plan(DOMAIN_EXCLUSION_EVAL_DIR / "repo", goal)
    contract = result.contract
    assert contract is not None
    assert contract.original_request == goal
    assert contract.explicit_requirements == [goal]
    assert not any("web" in r.lower() for r in contract.explicit_requirements)
    assert "src/sample_app/cli.py" in contract.recommended_scope
    assert (
        "src/sample_app/search/tavily.py"
        in contract.existing_capability_files
    )
    assert contract.assumptions == []
    assert contract.unresolved_questions == []

    skill = skill_template_text()
    assert "Requirement Fidelity" in skill

    instructions = format_instructions(contract, ".project-guard-skill.md")
    assert ".project-guard-skill.md" in instructions
    assert goal in instructions

    loaded = EngineeringContract.model_validate_json(
        contract.model_dump_json()
    )
    assert loaded == contract


def test_e2e_contract_parallel_implementation_remediation(tmp_path):
    """A simulated parallel implementation inside scope produces a reuse
    warning, a remediation constraint, and MEDIUM risk."""
    repo = _init_git_repo(DOMAIN_EXCLUSION_EVAL_DIR / "repo", tmp_path)
    goal = _load_expected(DOMAIN_EXCLUSION_EVAL_DIR)["goal"]
    contract = analyze_plan(repo, goal).contract
    assert contract is not None
    snapshot = contract_to_snapshot(contract)

    _append(
        repo / "src/sample_app/cli.py",
        "\n\n"
        "class ExcludedDomainSearchProvider:\n"
        "    def __init__(self, exclude_domains=()):\n"
        "        self.exclude_domains = exclude_domains\n",
    )

    result = analyze_diff(repo)
    compliance = check_plan_compliance(snapshot, result)
    warnings = check_reuse_warnings(repo, snapshot, result)
    assert warnings
    constraints = build_remediation_constraints(compliance, warnings)
    assert any(
        c.finding_type == "duplicate_implementation"
        for c in constraints
    )
    risk = merge_risk(result.risk, "MEDIUM")
    assert risk == "MEDIUM"
