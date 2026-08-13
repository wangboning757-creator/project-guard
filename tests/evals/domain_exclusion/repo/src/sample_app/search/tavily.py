"""Tavily search provider with domain filtering support."""

from __future__ import annotations


class TavilySearchProvider:
    """Provider that supports include/exclude domain filters."""

    def __init__(
        self,
        include_domains: tuple[str, ...] = (),
        exclude_domains: tuple[str, ...] = (),
    ) -> None:
        self.include_domains = include_domains
        self.exclude_domains = exclude_domains

    def search(self, query: str) -> dict:
        """Return a search payload with domain filters applied."""
        payload: dict = {}

        if self.exclude_domains:
            payload["exclude_domains"] = list(self.exclude_domains)

        return payload
