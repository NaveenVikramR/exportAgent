"""One live Tavily search.

Usage (from backend/):  python -m scripts.smoke_tavily
"""

import sys

from app.services.tavily_client import TavilyError, search


def main() -> int:
    query = "textile and apparel labelling requirements for imports into Germany"
    try:
        response = search(query, max_results=3)
    except TavilyError as exc:
        print(f"FAILED: {exc}")
        return 1

    print(f"query:  {response.query}")
    print(f"answer: {response.answer}")
    for hit in response.hits:
        print(f"  - {hit.title}\n    {hit.url}")
    if not response.hits:
        print("FAILED: no results returned")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
