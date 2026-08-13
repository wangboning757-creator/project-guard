"""Research workflow that enforces source limits."""

from .research_state import ResearchLimits


def run_research(limits: ResearchLimits) -> list[str]:
    """Run the research pipeline and enforce the source limit."""
    sources = fetch_sources(limits.max_sources)
    return sources[: limits.max_sources]


def fetch_sources(max_sources: int) -> list[str]:
    """Fetch up to max_sources sources."""
    return []
