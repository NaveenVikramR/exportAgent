from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.rate_limit import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, SpendCapExceeded, get_router
from app.models import Draft, Email, LLMCall
from app.services.drafting import DraftingError, approve, generate_drafts, recheck, reject

router = APIRouter(tags=["drafts"])


class DraftOut(BaseModel):
    id: int
    email_id: int
    order_id: int | None
    kind: str
    subject: str | None
    body: str
    edited_body: str | None
    # what would be sent: the reviewer's edit if there is one
    text: str
    status: str
    checked: int
    violations: list[dict[str, Any]]
    reviewed_by: str | None
    reviewed_at: datetime | None
    sent_at: datetime | None
    reject_reason: str | None
    created_at: datetime
    model: str | None = None
    cost_usd: Decimal | None = None
    email_subject: str | None = None
    email_sender: str | None = None


class EditIn(BaseModel):
    body: str = Field(min_length=1)


class ApproveIn(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)
    # approving a draft the fact check flagged needs an explicit acknowledgement
    acknowledge_violations: bool = False


class RejectIn(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str | None = None


def draft_out(session: Session, draft: Draft) -> DraftOut:
    check = draft.fact_check or {}
    call = session.get(LLMCall, draft.call_id) if draft.call_id else None
    email = session.get(Email, draft.email_id)
    return DraftOut(
        id=draft.id, email_id=draft.email_id, order_id=draft.order_id, kind=draft.kind, subject=draft.subject,
        body=draft.body, edited_body=draft.edited_body,
        text=draft.edited_body if draft.edited_body is not None else draft.body,
        status=draft.status, checked=check.get("checked", 0), violations=check.get("violations", []),
        reviewed_by=draft.reviewed_by, reviewed_at=draft.reviewed_at, sent_at=draft.sent_at,
        reject_reason=draft.reject_reason, created_at=draft.created_at,
        model=call.model if call else None, cost_usd=call.cost_usd if call else None,
        email_subject=email.subject if email else None, email_sender=email.sender if email else None,
    )


def _pending_or_409(session: Session, draft_id: int) -> Draft:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    if draft.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"This draft is already {draft.status}.")
    return draft


@router.post("/emails/{email_id}/drafts", response_model=list[DraftOut], dependencies=[Depends(rate_limit)])
def create_drafts(
    email_id: int,
    force: bool = False,
    session: Session = Depends(get_session),
    llm: LLMRouter = Depends(get_router),
) -> list[DraftOut]:
    """Draft a reply (and an internal note for order emails). Returns pending drafts unless `force`."""
    email = session.get(Email, email_id)
    if email is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found.")
    pending = session.scalars(select(Draft).where(Draft.email_id == email_id, Draft.status == "pending")).all()
    if pending and not force:
        return [draft_out(session, d) for d in pending]
    try:
        drafts = generate_drafts(session, email, llm)
    except DraftingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SpendCapExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return [draft_out(session, d) for d in drafts]


@router.get("/emails/{email_id}/drafts", response_model=list[DraftOut])
def email_drafts(email_id: int, session: Session = Depends(get_session)) -> list[DraftOut]:
    drafts = session.scalars(
        select(Draft).where(Draft.email_id == email_id, Draft.status != "superseded").order_by(Draft.id)
    )
    return [draft_out(session, d) for d in drafts]


@router.get("/drafts", response_model=list[DraftOut])
def queue(draft_status: str = "pending", session: Session = Depends(get_session)) -> list[DraftOut]:
    """The approval queue (status=pending by default; also sent, rejected)."""
    drafts = session.scalars(select(Draft).where(Draft.status == draft_status).order_by(Draft.created_at, Draft.id))
    return [draft_out(session, d) for d in drafts]


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
def edit(draft_id: int, payload: EditIn, session: Session = Depends(get_session)) -> DraftOut:
    draft = _pending_or_409(session, draft_id)
    draft.edited_body = payload.body
    recheck(draft, session)
    session.commit()
    return draft_out(session, draft)


@router.post("/drafts/{draft_id}/approve", response_model=DraftOut)
def approve_draft(draft_id: int, payload: ApproveIn, session: Session = Depends(get_session)) -> DraftOut:
    draft = _pending_or_409(session, draft_id)
    violations = (draft.fact_check or {}).get("violations", [])
    if violations and not payload.acknowledge_violations:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The fact check found {len(violations)} value(s) not in the source data. Edit the draft or acknowledge them.",
        )
    approve(draft, payload.reviewer)
    email = session.get(Email, draft.email_id)
    if draft.kind == "buyer_reply" and email is not None:
        email.status = "replied"
    session.commit()
    return draft_out(session, draft)


@router.post("/drafts/{draft_id}/reject", response_model=DraftOut)
def reject_draft(draft_id: int, payload: RejectIn, session: Session = Depends(get_session)) -> DraftOut:
    draft = _pending_or_409(session, draft_id)
    reject(draft, payload.reviewer, payload.reason)
    session.commit()
    return draft_out(session, draft)
