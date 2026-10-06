"""Per-IP sliding-window rate limit for endpoints that trigger LLM work.

In-memory, so it is per process: enough for a single-instance demo.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import get_settings

_WINDOW_SECONDS = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)


def reset() -> None:
    _hits.clear()


def rate_limit(request: Request) -> None:
    limit = get_settings().rate_limit_per_minute
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = _hits[ip]
    while hits and now - hits[0] > _WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit reached ({limit} requests per minute). Please wait and try again.",
            headers={"Retry-After": str(int(_WINDOW_SECONDS))},
        )
    hits.append(now)
