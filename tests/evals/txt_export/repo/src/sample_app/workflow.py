"""Research workflow: runs the pipeline and writes the final report."""

from .writer import render_markdown, write_report


def run_workflow(topic: str) -> str:
    """Run the research workflow and write the final report."""
    report = render_markdown(topic, [])
    write_report("out.md", topic)
    return report
