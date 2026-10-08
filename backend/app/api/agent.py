from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.loop import run_agent
from app.api.rate_limit import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, SpendCapExceeded, get_router
from app.models import AgentRun, Email, LLMCall
from app.schemas.risk import AgentRunOut, AgentStepOut

router = APIRouter(prefix="/emails/{email_id}/agent", tags=["agent"])


def _latest_run(session: Session, email_id: int) -> AgentRun | None:
    return session.scalar(
        select(AgentRun).where(AgentRun.email_id == email_id).order_by(AgentRun.id.desc()).limit(1)
    )


def run_out(session: Session, run: AgentRun, notice: str | None = None) -> AgentRunOut:
    calls = {call.id: call for call in session.scalars(select(LLMCall).where(LLMCall.run_id == run.id))}
    steps = []
    for step in run.steps:
        out = AgentStepOut.model_validate(step)
        call = calls.get(step.call_id) if step.call_id else None
        if call is not None:
            out = out.model_copy(update={
                "model": call.model, "tier": call.tier, "input_tokens": call.input_tokens,
                "output_tokens": call.output_tokens, "latency_ms": call.latency_ms,
                "cost_usd": call.cost_usd, "call_source": call.source,
            })
        steps.append(out)
    return AgentRunOut.model_validate(run).model_copy(update={
        "steps": steps,
        "ultra_calls": sum(1 for call in calls.values() if call.tier == "ultra"),
        "total_cost_usd": sum((call.cost_usd for call in calls.values()), Decimal("0")),
        "notice": notice,
    })


def _email_with_order(session: Session, email_id: int) -> Email:
    email = session.get(Email, email_id)
    if email is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found.")
    if email.order_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is not linked to an order yet. Analyse it first; emails without PO data have no order to assess.",
        )
    return email


@router.get("", response_model=AgentRunOut)
def latest(email_id: int, session: Session = Depends(get_session)) -> AgentRunOut:
    run = _latest_run(session, email_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No risk assessment yet.")
    return run_out(session, run)


@router.post("", response_model=AgentRunOut, dependencies=[Depends(rate_limit)])
def assess(
    email_id: int,
    force: bool = False,
    session: Session = Depends(get_session),
    llm: LLMRouter = Depends(get_router),
) -> AgentRunOut:
    """Run the risk agent. Returns the stored assessment unless `force` asks for a fresh run."""
    email = _email_with_order(session, email_id)
    previous = _latest_run(session, email_id)
    if previous is not None and previous.status in ("completed", "needs_review") and not force:
        return run_out(session, previous, notice="Showing the stored risk assessment.")
    try:
        run = run_agent(session, email, llm)
    except SpendCapExceeded as exc:
        if previous is not None and previous.result is not None:
            return run_out(session, previous, notice=f"{exc} Showing the stored risk assessment.")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return run_out(session, run)
