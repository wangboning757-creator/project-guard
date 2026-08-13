"""CLI entry point for research runs."""

import typer

from .workflow import run_research

app = typer.Typer()


def main() -> None:
    """Start a research run."""
    typer.run(run_research)


def research(domains: list[str] = typer.Option([], "--domain")) -> None:
    """Run research with domain filtering options."""
    run_research(domains)
