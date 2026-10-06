from decimal import Decimal

import pytest
from sqlalchemy import select

from app.llm.router import LLMRouter, SpendCapExceeded
from app.llm.tasks import TaskType
from app.models import LLMCall
from tests.test_router import MESSAGES, FakeClient


def _sources(session_factory) -> list[str]:
    with session_factory() as session:
        return [row.source for row in session.scalars(select(LLMCall).order_by(LLMCall.id))]


def test_mock_mode_makes_no_client_call_and_costs_nothing(settings, session_factory):
    settings.llm_mode = "mock"
    settings.nebius_api_key = None
    client = FakeClient()
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    result = router.complete(TaskType.DRAFT_REPLY, MESSAGES, max_tokens=64)

    assert client.calls == []
    assert result.source == "mock"
    assert result.cost_usd == 0
    assert _sources(session_factory) == ["mock"]


def test_identical_request_is_served_from_cache(settings, session_factory):
    client = FakeClient()
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    first = router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)
    second = router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)

    assert len(client.calls) == 1
    assert (first.source, second.source) == ("live", "cache")
    assert second.content == first.content
    assert second.cost_usd == 0
    assert _sources(session_factory) == ["live", "cache"]


def test_different_request_is_not_served_from_cache(settings, session_factory):
    client = FakeClient()
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)
    router.complete(TaskType.CLASSIFY, [{"role": "user", "content": "other"}], max_tokens=64)

    assert len(client.calls) == 2


def test_cache_can_be_disabled(settings, session_factory):
    settings.llm_cache_enabled = False
    client = FakeClient()
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)
    router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)

    assert len(client.calls) == 2


def test_spend_cap_blocks_live_calls_but_cached_requests_still_serve(settings, session_factory):
    # 1000 in + 500 out on nano = $0.00018 per call
    settings.daily_spend_cap_usd = Decimal("0.0003")
    client = FakeClient()
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)
    router.complete(TaskType.CLASSIFY, [{"role": "user", "content": "second"}], max_tokens=64)
    assert router.spent_today() == Decimal("0.00036")

    with pytest.raises(SpendCapExceeded, match="spend cap"):
        router.complete(TaskType.CLASSIFY, [{"role": "user", "content": "third"}], max_tokens=64)
    assert len(client.calls) == 2

    cached = router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)
    assert cached.source == "cache"


def test_cache_hits_do_not_count_towards_spend(settings, session_factory):
    router = LLMRouter(settings, client=FakeClient(), session_factory=session_factory)

    router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)
    router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)

    assert router.spent_today() == Decimal("0.00018")
