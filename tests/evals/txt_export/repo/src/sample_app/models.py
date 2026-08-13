"""Data models for research runs and their report documents."""


class ReportSection:
    """A single section of a report document."""

    def __init__(self, title: str) -> None:
        self.title = title


class ResearchRun:
    """Metadata for one research run and the report it produced."""

    def __init__(self, topic: str, section_count: int) -> None:
        self.topic = topic
        self.section_count = section_count
