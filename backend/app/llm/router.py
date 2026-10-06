"""Single entry point for every LLM call.

Callers declare a task type; the router picks the Nemotron tier from config,
calls Nebius Token Factory through the OpenAI-compatible SDK, and logs the
call (task, model, tokens, latency, estimated cost) to the `llm_calls` table.

Before a live call it checks the response cache and the daily spend cap, in
that order, so already-computed requests keep working once the cap is hit.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from openai import OpenAI, OpenAIError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.llm.mock import estimate_tokens, mock_completion
from app.llm.pricing import estimate_cost
from app.llm.tasks import DEFAULT_TASK_TIERS, TaskType, Tier
from app.models import LLMCache, LLMCall

logger = logging.getLogger(__name__)

_CACHEABLE_FINISH_REASONS = {"stop", "tool_calls"}


class LLMError(RuntimeError):
    """A Token Factory call failed or could not be made."""


class SpendCapExceeded(LLMError):
    """Today's live spend has reached DAILY_SPEND_CAP_USD."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LLMResult:
    task: TaskType
    tier: Tier
    model: str
    content: str | None
    finish_reason: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: Decimal
    # live | cache | mock
    source: str = "live"
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str | None = None
    call_id: int | None = None


class LLMRouter:
    def __init__(
        self,
        settings: Settings | None = None,
        client: OpenAI | None = None,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._session_factory = session_factory

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if not self.settings.nebius_api_key:
                raise LLMError("NEBIUS_API_KEY is not set. Add it to .env.")
            self._client = OpenAI(
                base_url=self.settings.nebius_base_url,
                api_key=self.settings.nebius_api_key,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=2,
            )
        return self._client

    def tier_for(self, task: TaskType) -> Tier:
        if self.settings.llm_force_tier is not None:
            return self.settings.llm_force_tier
        override = self.settings.llm_task_tier_overrides.get(task)
        return override or DEFAULT_TASK_TIERS[task]

    def routing_table(self) -> dict[TaskType, tuple[Tier, str]]:
        return {
            task: (self.tier_for(task), self.settings.model_for(self.tier_for(task)))
            for task in TaskType
        }

    def spent_today(self) -> Decimal:
        """Live spend since 00:00 UTC."""
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        with self._session_factory() as session:
            total = session.scalar(
                select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).where(
                    LLMCall.source == "live", LLMCall.created_at >= start
                )
            )
        return Decimal(str(total))

    def complete(
        self,
        task: TaskType,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float = 0.2,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        reasoning: bool | None = None,
        run_id: int | None = None,
    ) -> LLMResult:
        """Run one chat completion for `task` and log it.

        `reasoning` toggles Nemotron's thinking for this request; None leaves
        the model default.
        """
        tier = self.tier_for(task)
        model = self.settings.model_for(tier)

        if self.settings.llm_mode == "mock":
            return self._complete_mock(task, tier, model, messages, run_id)

        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            request["tools"] = tools
        if response_format:
            request["response_format"] = response_format
        if reasoning is not None:
            request["extra_body"] = {"chat_template_kwargs": {"enable_thinking": reasoning}}

        cache_key = _cache_key(request) if self.settings.llm_cache_enabled else None
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return self._result_from_payload(
                    cached, task=task, tier=tier, model=model, run_id=run_id,
                    source="cache", latency_ms=0, cost=Decimal("0"),
                )

        cap = self.settings.daily_spend_cap_usd
        if self.spent_today() >= cap:
            raise SpendCapExceeded(
                f"Daily LLM spend cap of ${cap} reached. Live calls resume at 00:00 UTC."
            )

        client = self.client
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(**request)
        except OpenAIError as exc:
            latency_ms = round((time.perf_counter() - started) * 1000)
            self._log(
                run_id=run_id, task=task, tier=tier, model=model, latency_ms=latency_ms,
                success=False, error=str(exc),
            )
            raise LLMError(f"Token Factory call failed ({model}): {exc}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000)

        usage = response.usage
        choice = response.choices[0]
        payload = {
            "content": choice.message.content,
            "finish_reason": choice.finish_reason,
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "tool_calls": [
                {"id": call.id, "name": call.function.name, "arguments": call.function.arguments}
                for call in (choice.message.tool_calls or [])
            ],
            "reasoning": getattr(choice.message, "reasoning_content", None),
        }
        cost = estimate_cost(
            payload["input_tokens"], payload["output_tokens"], *self.settings.prices_for(tier)
        )
        if cache_key and choice.finish_reason in _CACHEABLE_FINISH_REASONS:
            self._cache_put(cache_key, model, payload)

        return self._result_from_payload(
            payload, task=task, tier=tier, model=model, run_id=run_id,
            source="live", latency_ms=latency_ms, cost=cost,
        )

    def _complete_mock(
        self,
        task: TaskType,
        tier: Tier,
        model: str,
        messages: list[dict[str, Any]],
        run_id: int | None,
    ) -> LLMResult:
        started = time.perf_counter()
        content = mock_completion(task, messages)
        payload = {
            "content": content,
            "finish_reason": "stop",
            "input_tokens": estimate_tokens(json.dumps(messages)),
            "output_tokens": estimate_tokens(content),
        }
        return self._result_from_payload(
            payload, task=task, tier=tier, model=model, run_id=run_id, source="mock",
            latency_ms=round((time.perf_counter() - started) * 1000), cost=Decimal("0"),
        )

    def _result_from_payload(
        self,
        payload: dict[str, Any],
        *,
        task: TaskType,
        tier: Tier,
        model: str,
        run_id: int | None,
        source: str,
        latency_ms: int,
        cost: Decimal,
    ) -> LLMResult:
        call_id = self._log(
            run_id=run_id, task=task, tier=tier, model=model, latency_ms=latency_ms,
            input_tokens=payload["input_tokens"], output_tokens=payload["output_tokens"],
            cost_usd=cost, source=source,
        )
        return LLMResult(
            task=task,
            tier=tier,
            model=model,
            content=payload.get("content"),
            finish_reason=payload.get("finish_reason"),
            input_tokens=payload["input_tokens"],
            output_tokens=payload["output_tokens"],
            latency_ms=latency_ms,
            cost_usd=cost,
            source=source,
            tool_calls=[ToolCall(**call) for call in payload.get("tool_calls") or []],
            reasoning=payload.get("reasoning"),
            call_id=call_id,
        )

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        try:
            with self._session_factory() as session:
                row = session.get(LLMCache, key)
                return row.response if row else None
        except SQLAlchemyError:
            logger.exception("LLM cache read failed")
            return None

    def _cache_put(self, key: str, model: str, payload: dict[str, Any]) -> None:
        try:
            with self._session_factory() as session:
                session.merge(LLMCache(key=key, model=model, response=payload))
                session.commit()
        except SQLAlchemyError:
            logger.exception("LLM cache write failed")

    def _log(
        self,
        *,
        run_id: int | None,
        task: TaskType,
        tier: Tier,
        model: str,
        latency_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: Decimal = Decimal("0"),
        source: str = "live",
        success: bool = True,
        error: str | None = None,
    ) -> int | None:
        # Own session, so the log row survives a rollback in the caller's transaction.
        try:
            with self._session_factory() as session:
                row = LLMCall(
                    run_id=run_id,
                    task_type=task.value,
                    tier=tier.value,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    cost_usd=cost_usd,
                    source=source,
                    success=success,
                    error=error,
                )
                session.add(row)
                session.commit()
                return row.id
        except SQLAlchemyError:
            logger.exception("Could not write llm_calls row for task %s", task.value)
            return None


def _cache_key(request: dict[str, Any]) -> str:
    canonical = json.dumps(request, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
