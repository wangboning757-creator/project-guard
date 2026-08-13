"""CLI entry point for research runs."""

import typer

from .research_state import ResearchLimits
from .workflow import run_research

app = typer.Typer()


def main() -> None:
    """Start a research run."""
    typer.run(run_research)


def research(
    max_sources: int = typer.Option(10, "--max-sources"),
) -> None:
    """Run research limited to the maximum number of sources."""
    run_research(ResearchLimits(max_sources=max_sources))
