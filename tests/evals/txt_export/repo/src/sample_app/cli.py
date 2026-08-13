"""CLI entry point with commands for running research and resuming sessions."""

import typer

from .writer import render_markdown, write_report

app = typer.Typer()


def main() -> None:
    """Print the final report to the console."""
    typer.echo(render_markdown("topic", []))


def resume() -> None:
    """Resume a session and write its report to disk."""
    write_report("resume.md", "topic")
