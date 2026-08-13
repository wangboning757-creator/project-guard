"""Report writer for research runs."""

from __future__ import annotations


def write_report(path: str, sources: list[str]) -> str:
    """Write the research report listing the sources."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(sources))
    return path
