"""Web routes that consume research search results."""


def search_results_route(query: str, domains: list[str]) -> dict:
    """Render search results for the web UI."""
    return {"query": query, "domains": domains}
