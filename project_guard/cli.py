"""project-guard CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer

from . import __version__
from . import context as context_mod
from . import instructions, planner, reviewer, scanner, scoring

app = typer.Typer(
    help="Small local-first AI coding governance CLI.",
    no_args_is_help=True,
)


@app.command()
def inspect(path: Path = typer.Argument(".", help="Project directory")):
    """Analyze a project and print a health report."""
    typer.echo(scanner.format_inspect(scanner.scan_project(path)))


@app.command()
def context(path: Path = typer.Argument(".", help="Project directory")):
    """Generate a compact Markdown context for coding agents."""
    typer.echo(context_mod.build_context(path, scanner.scan_project(path)))


@app.command()
def plan(
    path: Path = typer.Argument(".", help="Project directory"),
    request: str = typer.Argument(
        ..., help="Feature request to check before implementation"
    ),
    output_plan: Path | None = typer.Option(
        None,
        "--output-plan",
        help="Write a plan snapshot JSON to this file (no auto-persist)",
    ),
    output_instructions: Path | None = typer.Option(
        None,
        "--output-instructions",
        help="Write agent instructions Markdown to this file (no auto-persist)",
    ),
    output_contract: Path | None = typer.Option(
        None,
        "--output-contract",
        help="Write the Engineering Contract JSON to this file "
        "(no auto-persist)",
    ),
    output_skill: Path | None = typer.Option(
        None,
        "--output-skill",
        help="Copy the fixed Coding Skill template to this file",
    ),
):
    """Check a feature request before implementation."""
    result = planner.analyze_plan(path, request)
    if output_plan is not None:
        snapshot = result.snapshot
        if snapshot is None:
            typer.echo("Error: no plan snapshot available", err=True)
            raise typer.Exit(1)
        try:
            output_plan.write_text(
                snapshot.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            typer.echo(f"Error: cannot write plan snapshot: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"Plan snapshot written to {output_plan}")
    if output_contract is not None:
        contract = result.contract
        if contract is None:
            typer.echo("Error: no engineering contract available", err=True)
            raise typer.Exit(1)
        try:
            output_contract.write_text(
                contract.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            typer.echo(
                f"Error: cannot write engineering contract: {exc}", err=True
            )
            raise typer.Exit(1) from exc
        typer.echo(f"Engineering contract written to {output_contract}")
    if output_skill is not None:
        try:
            output_skill.write_text(
                instructions.skill_template_text(),
                encoding="utf-8",
            )
        except OSError as exc:
            typer.echo(f"Error: cannot write coding skill: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"Coding skill written to {output_skill}")
    if output_instructions is not None:
        contract = result.contract
        if contract is None:
            typer.echo("Error: no engineering contract available", err=True)
            raise typer.Exit(1)
        skill_path = output_skill or Path(".project-guard-skill.md")
        try:
            output_instructions.write_text(
                instructions.format_instructions(contract, skill_path),
                encoding="utf-8",
            )
        except OSError as exc:
            typer.echo(
                f"Error: cannot write agent instructions: {exc}", err=True
            )
            raise typer.Exit(1) from exc
        typer.echo(f"Agent instructions written to {output_instructions}")
    typer.echo(planner.format_plan(result))


@app.command()
def review(
    path: Path = typer.Argument(".", help="Git project directory"),
    plan: Path | None = typer.Option(
        None,
        "--plan",
        help="Plan snapshot JSON to check diff compliance against",
    ),
    instructions: Path | None = typer.Option(
        None,
        "--instructions",
        help="Agent instructions file to exclude from review diff.",
    ),
    contract: Path | None = typer.Option(
        None,
        "--contract",
        help="Engineering Contract JSON to check the diff against",
    ),
    skill: Path | None = typer.Option(
        None,
        "--skill",
        help="Coding Skill file to exclude from review diff.",
    ),
    task_contract: Path | None = typer.Option(
        None,
        "--task-contract",
        help="Agent-maintained Task Contract JSON with approved scope "
        "amendments",
    ),
):
    """Analyze the current git diff for risk signals."""
    snapshot = None
    engineering_contract = None
    task_contract_obj = None
    if contract is not None:
        try:
            engineering_contract = reviewer.load_engineering_contract(
                contract
            )
        except reviewer.ContractError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        snapshot = reviewer.contract_to_snapshot(engineering_contract)
    elif plan is not None:
        try:
            snapshot = reviewer.load_plan_snapshot(plan)
        except reviewer.PlanSnapshotError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
    if task_contract is not None:
        if engineering_contract is None:
            typer.echo(
                "Error: --task-contract requires --contract",
                err=True,
            )
            raise typer.Exit(1)
        try:
            task_contract_obj = reviewer.load_task_contract(task_contract)
        except reviewer.TaskContractError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        if (
            task_contract_obj.original_request
            != engineering_contract.original_request
        ):
            typer.echo("Task Contract mismatch:", err=True)
            typer.echo(
                "original_request does not match Guard Contract.",
                err=True,
            )
            raise typer.Exit(1)
    exclude_paths: set[Path] = set()
    if plan is not None:
        exclude_paths.add(plan)
    if contract is not None:
        exclude_paths.add(contract)
    if task_contract is not None:
        exclude_paths.add(task_contract)
    for artifact in (instructions, skill):
        if artifact is not None:
            if not artifact.is_file():
                typer.echo(
                    f"Error: file not found: {artifact}",
                    err=True,
                )
                raise typer.Exit(1)
            exclude_paths.add(artifact)
    try:
        result = reviewer.analyze_diff(
            path,
            exclude_paths=exclude_paths or None,
        )
    except reviewer.NotAGitRepoError as exc:
        typer.echo(f"Error: not a git repository ({exc})", err=True)
        raise typer.Exit(1) from exc
    if snapshot is not None:
        amendments = (
            task_contract_obj.scope_amendments
            if task_contract_obj is not None
            else None
        )
        compliance = reviewer.check_plan_compliance(
            snapshot, result, amendments=amendments
        )
        reuse_warnings = reviewer.check_reuse_warnings(
            path, snapshot, result
        )
        if reuse_warnings:
            compliance.reuse_warnings = reuse_warnings
            compliance.risk = reviewer.merge_risk(compliance.risk, "MEDIUM")
        final_risk = reviewer.merge_risk(result.risk, compliance.risk)
        complexity = None
        if engineering_contract is not None:
            complexity = reviewer.check_complexity(
                path, engineering_contract, result
            )
            if complexity.level == "MEDIUM":
                final_risk = reviewer.merge_risk(final_risk, "MEDIUM")
            fidelity = reviewer.check_requirement_fidelity(
                engineering_contract, result
            )
            constraints = reviewer.build_remediation_constraints(
                compliance, reuse_warnings
            )
        extra_reasons: list[str] = []
        if reuse_warnings:
            extra_reasons.extend(reuse_warnings)
        if complexity is not None and complexity.level == "MEDIUM":
            extra_reasons.append("complexity signal: MEDIUM")
        if compliance.risk in ("MEDIUM", "HIGH") and compliance.violations:
            extra_reasons.extend(compliance.violations)
        typer.echo(
            reviewer.format_review(
                result,
                risk=final_risk,
                extra_reasons=extra_reasons,
            )
        )
        typer.echo("")
        typer.echo(reviewer.format_plan_compliance(compliance))
        if engineering_contract is not None:
            typer.echo("")
            typer.echo(f"Requirement Fidelity: {fidelity}")
            if fidelity == "STRUCTURAL CHECK ONLY":
                typer.echo("No obvious structural conflict found.")
            typer.echo(
                "Semantic correctness is not determined by Project Guard."
            )
            typer.echo("")
            typer.echo(
                reviewer.format_complexity(
                    complexity, engineering_contract
                )
            )
            typer.echo("")
            typer.echo(reviewer.format_quality_signals(path, result))
            typer.echo("")
            typer.echo(reviewer.format_remediation_constraints(constraints))
    else:
        typer.echo(reviewer.format_review(result))


@app.command()
def score(path: Path = typer.Argument(".", help="Project directory")):
    """Print an AI coding readiness score."""
    scan = scanner.scan_project(path)
    diff = None
    try:
        diff = reviewer.analyze_diff(path)
    except (reviewer.NotAGitRepoError, RuntimeError):
        diff = None
    typer.echo(scoring.format_score(scoring.compute_score(scan, diff)))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
