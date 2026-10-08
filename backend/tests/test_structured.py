from decimal import Decimal

import pytest

from app.llm.router import LLMResult
from app.llm.structured import StructuredOutputError, complete_structured
from app.llm.tasks import TaskType, Tier
from app.schemas.extraction import Classification

VALID = '{"category": "new_po", "intents": ["new_po"], "has_po_data": true, "summary": "s", "confidence": 0.9}'
MESSAGES = [{"role": "user", "content": "email"}]


class ScriptedRouter:
    """Returns the given replies in order and records the messages it was sent."""

    def __init__(self, replies: list[str]):
        self._replies = iter(replies)
        self.requests: list[list[dict]] = []

    def complete(self, task, messages, **_kwargs) -> LLMResult:
        self.requests.append(list(messages))
        return LLMResult(
            task=task, tier=Tier.NANO, model="test/nano", content=next(self._replies),
            finish_reason="stop", input_tokens=1, output_tokens=1, latency_ms=1, cost_usd=Decimal("0"),
        )


def _run(router):
    return complete_structured(router, TaskType.CLASSIFY, MESSAGES, Classification, max_tokens=100)


def test_valid_reply_is_parsed_in_one_call():
    router = ScriptedRouter([VALID])

    result = _run(router)

    assert result.category == "new_po"
    assert len(router.requests) == 1


def test_json_wrapped_in_a_code_fence_is_accepted():
    router = ScriptedRouter([f"Here you go:\n```json\n{VALID}\n```"])

    assert _run(router).has_po_data is True


def test_invalid_reply_is_retried_once_with_the_validation_error():
    router = ScriptedRouter(['{"category": "purchase"}', VALID])

    result = _run(router)

    assert result.category == "new_po"
    assert len(router.requests) == 2
    retry = router.requests[1]
    assert retry[-2] == {"role": "assistant", "content": '{"category": "purchase"}'}
    assert "failed validation" in retry[-1]["content"]
    assert "category" in retry[-1]["content"]


def test_two_invalid_replies_raise_for_human_review():
    router = ScriptedRouter(["not json", "still not json"])

    with pytest.raises(StructuredOutputError, match="after one retry"):
        _run(router)
    assert len(router.requests) == 2


def test_reasoning_setting_is_passed_to_the_router():
    seen = []

    class Recording(ScriptedRouter):
        def complete(self, task, messages, **kwargs):
            seen.append(kwargs.get("reasoning"))
            return super().complete(task, messages, **kwargs)

    complete_structured(Recording([VALID]), TaskType.CLASSIFY, MESSAGES, Classification,
                        max_tokens=100, reasoning=False)

    assert seen == [False]


def test_category_is_always_included_in_intents():
    reply = '{"category": "new_po", "intents": ["payment"], "has_po_data": true, "summary": "s", "confidence": 1}'

    result = _run(ScriptedRouter([reply]))

    assert [i.value for i in result.intents] == ["new_po", "payment"]
