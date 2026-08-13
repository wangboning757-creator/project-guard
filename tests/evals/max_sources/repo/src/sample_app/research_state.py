"""Research state and limits shared across a run."""

from dataclasses import dataclass


@dataclass
class ResearchLimits:
    """Limits applied during a research run."""

    max_sources: int = 10
    max_depth: int = 3
