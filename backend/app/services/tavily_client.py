"""Tavily web search, used for compliance and buyer lookups. Always returns source URLs."""

from dataclasses import dataclass, field
from typing import Any

from tavily import TavilyClient

from app.config import get_settings


class TavilyError(RuntimeError):
    """A Tavily search failed or could not be made."""


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    content: str
    score: float | None = None


@dataclass(frozen=True)
class SearchResponse:
    query: str
    answer: str | None
    hits: list[SearchHit] = field(default_factory=list)

    @property
    def source_urls(self) -> list[str]:
        return [hit.url for hit in self.hits]


def search(
    query: str,
    *,
    max_results: int = 5,
    search_depth: str = "basic",
    include_domains: list[str] | None = None,
    client: Any | None = None,
) -> SearchResponse:
    if client is None:
        api_key = get_settings().tavily_api_key
        if not api_key:
            raise TavilyError("TAVILY_API_KEY is not set. Add it to .env.")
        client = TavilyClient(api_key=api_key)

    kwargs: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": True,
    }
    if include_domains:
        kwargs["include_domains"] = include_domains

    # The SDK raises its own error types plus raw HTTP errors; wrap them all so
    # callers only have one failure to handle.
    try:
        raw = client.search(**kwargs)
    except Exception as exc:
        raise TavilyError(f"Tavily search failed: {exc}") from exc

    hits = [
        SearchHit(
            title=item.get("title", ""),
            url=item["url"],
            content=item.get("content", ""),
            score=item.get("score"),
        )
        for item in raw.get("results", [])
        if item.get("url")
    ]
    return SearchResponse(query=query, answer=raw.get("answer"), hits=hits)
