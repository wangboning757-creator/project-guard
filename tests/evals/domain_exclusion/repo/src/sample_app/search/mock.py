"""In-memory mock search provider."""

from .base import SearchProvider


class MockSearchProvider(SearchProvider):
    """Mock provider that returns no results."""

    def search(self, query: str) -> dict:
        """Return an empty payload."""
        return {}
