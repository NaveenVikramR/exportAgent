"""One call for the landing page: what needs attention, and what the AI cost today."""

from datetime import UTC, datetime, time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.emails import _summary
from app.config import get_settings
from app.db import get_session
from app.llm.router import get_router
from app.models import AgentRun, Draft, Email, LLMCall, Order
from app.services.orders import match_question

router = APIRouter(tags=["dashboard"])

# The case_002 story: a revised PO that pulls the date forward and cannot be made in time.
DEMO_STORY_EXTERNAL_ID = "case_002"


def calls_today(session: Session) -> int:
    start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    return session.scalar(select(func.count()).select_from(LLMCall).where(LLMCall.created_at >= start)) or 0


def _high_risks(session: Session) -> list[dict[str, Any]]:
    """High flags in the latest assessment of each email."""
    latest = (
        select(AgentRun.email_id, func.max(AgentRun.id).label("run_id"))
        .group_by(AgentRun.email_id)
        .subquery()
    )
    rows = []
    for run in session.scalars(select(AgentRun).join(latest, AgentRun.id == latest.c.run_id).order_by(AgentRun.id.desc())):
        order = session.get(Order, run.order_id) if run.order_id else None
        for flag in (run.result or {}).get("flags", []):
            if flag.get("severity") == "high":
                rows.append({
                    "email_id": run.email_id, "order_id": run.order_id,
                    "po_number": order.po_number if order else None, "buyer": order.buyer if order else None,
                    "category": flag["category"], "reason": flag["reason"],
                })
    return rows


@router.get("/dashboard")
def dashboard(session: Session = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings()
    llm = get_router()
    emails = list(session.scalars(select(Email).where(Email.match.is_not(None))))
    demo = session.scalar(select(Email.id).where(Email.external_id == DEMO_STORY_EXTERNAL_ID))
    return {
        "open_orders": session.scalar(select(func.count()).select_from(Order).where(Order.status != "confirmed")) or 0,
        "awaiting_buyer": session.scalar(select(func.count()).select_from(Order).where(Order.status == "awaiting_buyer")) or 0,
        "drafts_pending": session.scalar(select(func.count()).select_from(Draft).where(Draft.status == "pending")) or 0,
        "match_questions": sum(1 for email in emails if match_question(email)),
        "emails_to_review": session.scalar(select(func.count()).select_from(Email).where(Email.status == "needs_review")) or 0,
        "high_risks": _high_risks(session),
        "spend": {
            "today_usd": str(llm.spent_today()),
            "cap_usd": str(settings.daily_spend_cap_usd),
            "calls_today": calls_today(session),
            "llm_mode": settings.llm_mode,
        },
        "recent_emails": [_summary(e) for e in session.scalars(select(Email).order_by(Email.received_at.desc(), Email.id.desc()).limit(6))],
        "demo_email_id": demo,
        "demo_reset_enabled": settings.demo_reset_enabled,
    }

