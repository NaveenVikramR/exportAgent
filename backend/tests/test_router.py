from decimal import Decimal
from types import SimpleNamespace

import pytest
from openai import OpenAIError
from sqlalchemy import select

from app.llm.pricing import estimate_cost
from app.llm.router import LLMError, LLMRouter
from app.llm.tasks import DEFAULT_TASK_TIERS, TaskType, Tier
from app.models import LLMCall

MESSAGES = [{"role": "user", "content": "hello"}]


class FakeClient:
    def __init__(self, *, prompt_tokens=1000, completion_tokens=500, error=None):
        self.calls: list[dict] = []
        self._usage = SimpleNamespace(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        message = SimpleNamespace(content="ok", tool_calls=None)
        return SimpleNamespace(
            usage=self._usage,
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
        )


def test_estimate_cost_uses_per_million_prices():
    cost = estimate_cost(1000, 500, Decimal("0.30"), Decimal("0.90"))
    assert cost == Decimal("0.00075000")


def test_every_task_type_has_a_default_tier():
    assert set(DEFAULT_TASK_TIERS) == set(TaskType)


@pytest.mark.parametrize(
    ("task", "tier", "model"),
    [
        (TaskType.CLASSIFY, Tier.NANO, "test/nano"),
        (TaskType.EXTRACT, Tier.NANO, "test/nano"),
        (TaskType.CHANGE_DETECTION, Tier.NANO, "test/nano"),
        (TaskType.DRAFT_REPLY, Tier.SUPER, "test/super"),
        (TaskType.DRAFT_INTERNAL_NOTE, Tier.SUPER, "test/super"),
        (TaskType.RISK_REASONING, Tier.ULTRA, "test/ultra"),
        (TaskType.PLANNING, Tier.ULTRA, "test/ultra"),
    ],
)
def test_task_routes_to_expected_model(settings, session_factory, task, tier, model):
    client = FakeClient()
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    result = router.complete(task, MESSAGES, max_tokens=64)

    assert result.tier is tier
    assert result.model == model
    assert client.calls[0]["model"] == model
    assert client.calls[0]["max_tokens"] == 64


def test_force_tier_overrides_routing_table(settings, session_factory):
    settings.llm_force_tier = Tier.NANO
    router = LLMRouter(settings, client=FakeClient(), session_factory=session_factory)

    assert router.tier_for(TaskType.PLANNING) is Tier.NANO
    assert router.tier_for(TaskType.DRAFT_REPLY) is Tier.NANO


def test_per_task_override(settings, session_factory):
    settings.llm_task_tier_overrides = {TaskType.PLANNING: Tier.SUPER}
    router = LLMRouter(settings, client=FakeClient(), session_factory=session_factory)

    assert router.tier_for(TaskType.PLANNING) is Tier.SUPER
    assert router.tier_for(TaskType.RISK_REASONING) is Tier.ULTRA


def test_successful_call_is_logged_with_tokens_latency_and_cost(settings, session_factory):
    router = LLMRouter(settings, client=FakeClient(), session_factory=session_factory)

    result = router.complete(TaskType.DRAFT_REPLY, MESSAGES, max_tokens=64)

    with session_factory() as session:
        row = session.scalars(select(LLMCall)).one()
    assert row.id == result.call_id
    assert row.task_type == "draft_reply"
    assert row.tier == "super"
    assert row.model == "test/super"
    assert (row.input_tokens, row.output_tokens) == (1000, 500)
    assert row.latency_ms >= 0
    assert row.success is True
    # 1000 * 0.30/1M + 500 * 0.90/1M
    assert Decimal(row.cost_usd) == Decimal("0.00075")
    assert result.cost_usd == Decimal("0.00075")


def test_failed_call_is_logged_and_raises_llm_error(settings, session_factory):
    client = FakeClient(error=OpenAIError("upstream down"))
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    with pytest.raises(LLMError, match="upstream down"):
        router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)

    with session_factory() as session:
        row = session.scalars(select(LLMCall)).one()
    assert row.success is False
    assert "upstream down" in row.error
    assert row.cost_usd == 0


def test_reasoning_flag_is_sent_only_when_set(settings, session_factory):
    client = FakeClient()
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)
    router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64, reasoning=False)

    assert "extra_body" not in client.calls[0]
    assert client.calls[1]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_missing_api_key_raises_llm_error(settings, session_factory):
    settings.nebius_api_key = None
    router = LLMRouter(settings, session_factory=session_factory)

    with pytest.raises(LLMError, match="NEBIUS_API_KEY"):
        router.complete(TaskType.CLASSIFY, MESSAGES, max_tokens=64)
