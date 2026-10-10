"""Tavily lookups for the agent, cached by query so repeats cost no search credits."""

import hashlib
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.models import SearchCache
from app.services import tavily_client

_SNIPPET_CHARS = 400
_ANSWER_CHARS = 900


def cached_search(
    session: Session,
    query: str,
    *,
    max_results: int = 4,
    search: Callable[..., tavily_client.SearchResponse] = tavily_client.search,
    key: str | None = None,
) -> dict[str, Any]:
    """{"query", "answer", "sources": [{"title", "url", "snippet"}], "cached"}. Raises TavilyError.

    `key` overrides the cache key (callers pass a normalised, dated key); default is the query.
    """
    key = hashlib.sha256(f"{max_results}|{key or query}".encode("utf-8")).hexdigest()
    row = session.get(SearchCache, key)
    if row is not None:
        return {**row.response, "cached": True}

    response = search(query, max_results=max_results)
    result = {
        "query": query,
        "answer": (response.answer or "")[:_ANSWER_CHARS],
        "sources": [
            {"title": hit.title, "url": hit.url, "snippet": hit.content[:_SNIPPET_CHARS]}
            for hit in response.hits
        ],
    }
    session.merge(SearchCache(key=key, query=query, response=result))
    session.commit()
    return {**result, "cached": False}
