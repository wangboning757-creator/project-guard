"""Google provider for the research pipeline."""

from .base import SearchProvider


class GoogleProvider(SearchProvider):
    def search(self, query: str) -> list[str]:
        return []
