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
):
    """Check a feature request before implementation."""
    typer.echo(planner.format_plan(planner.analyze_plan(path, request)))


@app.command()
def review(path: Path = typer.Argument(".", help="Git project directory")):
    """Analyze the current git diff for risk signals."""
    try:
        result = reviewer.analyze_diff(path)
    except reviewer.NotAGitRepoError as exc:
        typer.echo(f"Error: not a git repository ({exc})", err=True)
        raise typer.Exit(1) from exc
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
