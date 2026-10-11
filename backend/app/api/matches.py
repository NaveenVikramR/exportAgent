from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Email
from app.services.orders import match_question, resolve_match

router = APIRouter(tags=["order matching"])


class MatchAnswer(BaseModel):
    # True: the email is about the candidate order; False: it is a new order
    same_order: bool
    decided_by: str = Field(min_length=1, max_length=100)


@router.get("/match-questions")
def questions(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Emails whose order could not be matched with confidence, waiting for a person."""
    rows = []
    for email in session.scalars(select(Email).where(Email.match.is_not(None)).order_by(Email.received_at)):
        question = match_question(email)
        if question:
            rows.append(question | {"subject": email.subject, "sender": email.sender})
    return rows


@router.post("/emails/{email_id}/match")
def answer(email_id: int, payload: MatchAnswer, session: Session = Depends(get_session)) -> dict[str, Any]:
    email = session.get(Email, email_id)
    if email is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found.")
    try:
        result = resolve_match(session, email, payload.same_order, payload.decided_by)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {
        "email_id": email.id,
        "order_id": result.order.id if result.order else None,
        "version": result.version.version if result.version else None,
        "same_order": payload.same_order,
    }
