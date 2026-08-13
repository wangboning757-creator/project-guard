"""Research workflow that runs searches and filters domains."""

from .search.tavily import TavilySearchProvider


def run_research(domains: list[str]) -> list[str]:
    """Run the research pipeline using the configured search provider."""
    provider = TavilySearchProvider()
    return provider.search("query")
