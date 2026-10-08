from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["high", "medium", "low"]
RiskCategory = Literal[
    "delivery", "capacity", "quantity", "price", "compliance", "buyer", "data_quality", "other"
]


class RiskFlag(BaseModel):
    severity: Severity
    category: RiskCategory
    reason: str = Field(max_length=300)
    # evidence ids of tool results (E1, E2, ...) and/or source URLs from those results
    evidence: list[str] = Field(default_factory=list)
    # set by Python after the run: does every evidence item point at something real?
    verified: bool = False
    # model: proposed by Ultra; rule: added by a Python safety rule
    source: Literal["model", "rule"] = "model"


class RiskReport(BaseModel):
    summary: str
    flags: list[RiskFlag] = Field(default_factory=list)


class AgentStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    round: int
    kind: str
    name: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    summary: str | None
    evidence_id: str | None
    call_id: int | None
    created_at: datetime
    # joined from the router's log row for llm steps
    model: str | None = None
    tier: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    cost_usd: Decimal | None = None
    call_source: str | None = None


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_id: int | None
    order_id: int | None
    status: str
    rounds: int
    result: RiskReport | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    steps: list[AgentStepOut] = Field(default_factory=list)
    ultra_calls: int = 0
    total_cost_usd: Decimal = Decimal("0")
    notice: str | None = None
