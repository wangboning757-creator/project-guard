"""project-guard CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer

from . import __version__
from . import context as context_mod
from . import planner, reviewer, scanner, scoring

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
    typer.echo(planner.format_plan(result))


@app.command()
def review(
    path: Path = typer.Argument(".", help="Git project directory"),
    plan: Path | None = typer.Option(
        None,
        "--plan",
        help="Plan snapshot JSON to check diff compliance against",
    ),
):
    """Analyze the current git diff for risk signals."""
    snapshot = None
    if plan is not None:
        try:
            snapshot = reviewer.load_plan_snapshot(plan)
        except reviewer.PlanSnapshotError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
    try:
        result = reviewer.analyze_diff(
            path,
            exclude_paths={plan} if plan is not None else None,
        )
    except reviewer.NotAGitRepoError as exc:
        typer.echo(f"Error: not a git repository ({exc})", err=True)
        raise typer.Exit(1) from exc
    if snapshot is not None:
        compliance = reviewer.check_plan_compliance(snapshot, result)
        final_risk = reviewer.merge_risk(result.risk, compliance.risk)
        typer.echo(reviewer.format_review(result, risk=final_risk))
        typer.echo("")
        typer.echo(reviewer.format_plan_compliance(compliance))
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
