"""Base class for search providers that fetch sources for research."""

from abc import ABC, abstractmethod


class SearchProvider(ABC):
    """Fetches sources used in research."""

    @abstractmethod
    def search(self, query: str) -> list[str]:
        """Return sources matching the query."""
        raise NotImplementedError
