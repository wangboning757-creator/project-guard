"""Background tasks for the research pipeline."""

from ..writer import render_markdown, write_report


def send_digest(topic: str) -> str:
    """Build and deliver the daily report digest."""
    return render_markdown(topic, [])


def archive(topic: str) -> None:
    """Archive the finished report to storage."""
    write_report("archive.md", topic)
