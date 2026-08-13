"""Bing provider for the research pipeline."""

from .base import SearchProvider


class BingProvider(SearchProvider):
    def search(self, query: str) -> list[str]:
        return []
