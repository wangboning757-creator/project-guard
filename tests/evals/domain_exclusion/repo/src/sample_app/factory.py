"""Factory that constructs configured search providers."""

from .search.tavily import TavilySearchProvider


def create_search_provider(
    exclude_domains: tuple[str, ...] = (),
) -> TavilySearchProvider:
    """Construct the configured search provider."""
    return TavilySearchProvider(exclude_domains=exclude_domains)
