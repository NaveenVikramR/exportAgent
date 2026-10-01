from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.llm.router import get_router
from app.models import LLMCall
from app.schemas.trace import LLMCallOut, ModelUsage, RouteOut, TraceSummary

router = APIRouter(prefix="/trace", tags=["trace"])


@router.get("/routes", response_model=list[RouteOut])
def routes() -> list[RouteOut]:
    """The live task -> tier -> model routing table."""
    return [
        RouteOut(task_type=task.value, tier=tier.value, model=model)
        for task, (tier, model) in get_router().routing_table().items()
    ]


@router.get("/calls", response_model=list[LLMCallOut])
def calls(
    limit: int = Query(50, ge=1, le=500),
    run_id: int | None = None,
    session: Session = Depends(get_session),
) -> list[LLMCall]:
    query = select(LLMCall).order_by(LLMCall.id.desc()).limit(limit)
    if run_id is not None:
        query = query.where(LLMCall.run_id == run_id)
    return list(session.scalars(query))


@router.get("/summary", response_model=TraceSummary)
def summary(session: Session = Depends(get_session)) -> TraceSummary:
    rows = session.execute(
        select(
            LLMCall.model,
            LLMCall.tier,
            func.count(LLMCall.id),
            func.coalesce(func.sum(LLMCall.input_tokens), 0),
            func.coalesce(func.sum(LLMCall.output_tokens), 0),
            func.coalesce(func.avg(LLMCall.latency_ms), 0),
            func.coalesce(func.sum(LLMCall.cost_usd), 0),
        )
        .group_by(LLMCall.model, LLMCall.tier)
        .order_by(LLMCall.model)
    ).all()
    by_model = [
        ModelUsage(
            model=model,
            tier=tier,
            calls=count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            avg_latency_ms=round(avg_latency),
            cost_usd=Decimal(str(cost)),
        )
        for model, tier, count, input_tokens, output_tokens, avg_latency, cost in rows
    ]
    return TraceSummary(
        total_calls=sum(usage.calls for usage in by_model),
        total_cost_usd=sum((usage.cost_usd for usage in by_model), Decimal("0")),
        by_model=by_model,
    )
