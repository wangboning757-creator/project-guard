"""Base class for search providers."""

from abc import ABC, abstractmethod


class SearchProvider(ABC):
    """Abstract search provider."""

    @abstractmethod
    def search(self, query: str) -> dict:
        """Run a search and return results."""
        raise NotImplementedError
