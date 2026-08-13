"""Report writer: renders research reports and exports them to files."""

from __future__ import annotations


def render_markdown(topic: str, sections: list[str]) -> str:
    """Render the final report as Markdown text."""
    return "\n".join(sections)


def write_report(path: str, topic: str) -> str:
    """Write the rendered report to a file and return the path."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(topic, []))
    return path


def export_report(path: str, topic: str) -> str:
    """Export the report document to the given path."""
    return write_report(path, topic)
