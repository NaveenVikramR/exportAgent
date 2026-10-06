from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class LLMCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int | None
    task_type: str
    tier: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: Decimal
    source: str
    success: bool
    error: str | None
    created_at: datetime


class ModelUsage(BaseModel):
    model: str
    tier: str
    source: str
    calls: int
    input_tokens: int
    output_tokens: int
    avg_latency_ms: int
    cost_usd: Decimal


class TraceSummary(BaseModel):
    total_calls: int
    total_cost_usd: Decimal
    llm_mode: str
    spent_today_usd: Decimal
    daily_spend_cap_usd: Decimal
    by_model: list[ModelUsage]


class RouteOut(BaseModel):
    task_type: str
    tier: str
    model: str
