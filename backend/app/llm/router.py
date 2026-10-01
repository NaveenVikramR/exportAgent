"""Single entry point for every LLM call.

Callers declare a task type; the router picks the Nemotron tier from config,
calls Nebius Token Factory through the OpenAI-compatible SDK, and logs the
call (task, model, tokens, latency, estimated cost) to the `llm_calls` table.
"""

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from openai import OpenAI, OpenAIError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.llm.pricing import estimate_cost
from app.llm.tasks import DEFAULT_TASK_TIERS, TaskType, Tier
from app.models import LLMCall

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """A Token Factory call failed or could not be made."""


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
    tool_calls: list[Any] = field(default_factory=list)
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
        client = self.client

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if response_format:
            kwargs["response_format"] = response_format
        if reasoning is not None:
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": reasoning}}

        started = time.perf_counter()
        try:
            response = client.chat.completions.create(**kwargs)
        except OpenAIError as exc:
            latency_ms = round((time.perf_counter() - started) * 1000)
            self._log(
                run_id=run_id,
                task=task,
                tier=tier,
                model=model,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )
            raise LLMError(f"Token Factory call failed ({model}): {exc}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000)

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = estimate_cost(input_tokens, output_tokens, *self.settings.prices_for(tier))

        call_id = self._log(
            run_id=run_id,
            task=task,
            tier=tier,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
        )

        choice = response.choices[0]
        return LLMResult(
            task=task,
            tier=tier,
            model=model,
            content=choice.message.content,
            finish_reason=choice.finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            tool_calls=list(choice.message.tool_calls or []),
            reasoning=getattr(choice.message, "reasoning_content", None),
            call_id=call_id,
        )

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
                    success=success,
                    error=error,
                )
                session.add(row)
                session.commit()
                return row.id
        except SQLAlchemyError:
            logger.exception("Could not write llm_calls row for task %s", task.value)
            return None


_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
