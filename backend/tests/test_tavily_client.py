import pytest

from app.services.tavily_client import TavilyError, search


class FakeTavily:
    def __init__(self, response=None, error=None):
        self.kwargs = None
        self._response = response
        self._error = error

    def search(self, **kwargs):
        self.kwargs = kwargs
        if self._error:
            raise self._error
        return self._response


def test_search_returns_hits_with_source_urls():
    client = FakeTavily(
        response={
            "answer": "Fibre composition labels are required.",
            "results": [
                {"title": "EU textile rules", "url": "https://example.eu/a", "content": "x", "score": 0.9},
                {"title": "No URL", "content": "dropped"},
            ],
        }
    )

    response = search("eu textile labelling", max_results=3, client=client)

    assert response.answer == "Fibre composition labels are required."
    assert response.source_urls == ["https://example.eu/a"]
    assert client.kwargs["max_results"] == 3
    assert client.kwargs["include_answer"] is True


def test_search_wraps_client_errors():
    client = FakeTavily(error=RuntimeError("rate limited"))

    with pytest.raises(TavilyError, match="rate limited"):
        search("anything", client=client)
