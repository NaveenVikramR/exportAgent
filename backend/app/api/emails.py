from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.rate_limit import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, SpendCapExceeded, get_router
from app.models import Email
from app.schemas.emails import EmailDetail, EmailSummary
from app.services.analysis import analyse_email

router = APIRouter(prefix="/emails", tags=["emails"])


def _review_count(email: Email) -> int:
    return len((email.extraction or {}).get("review") or [])


def _summary(email: Email) -> EmailSummary:
    return EmailSummary.model_validate(email).model_copy(update={"review_count": _review_count(email)})


def _detail(email: Email, notice: str | None = None) -> EmailDetail:
    return EmailDetail.model_validate(email).model_copy(
        update={"review_count": _review_count(email), "notice": notice}
    )


def _get_or_404(session: Session, email_id: int) -> Email:
    email = session.get(Email, email_id)
    if email is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found.")
    return email


@router.get("", response_model=list[EmailSummary])
def list_emails(session: Session = Depends(get_session)) -> list[EmailSummary]:
    emails = session.scalars(select(Email).order_by(Email.received_at.desc(), Email.id.desc()))
    return [_summary(email) for email in emails]


@router.get("/{email_id}", response_model=EmailDetail)
def get_email(email_id: int, session: Session = Depends(get_session)) -> EmailDetail:
    return _detail(_get_or_404(session, email_id))


@router.post("/{email_id}/analyse", response_model=EmailDetail, dependencies=[Depends(rate_limit)])
def analyse(
    email_id: int,
    force: bool = False,
    session: Session = Depends(get_session),
    llm: LLMRouter = Depends(get_router),
) -> EmailDetail:
    """Classify and extract. Returns the stored result unless `force` asks for a fresh run."""
    email = _get_or_404(session, email_id)
    if email.classification is not None and not force:
        return _detail(email, notice="Showing the stored analysis.")
    try:
        analyse_email(session, email, llm)
    except SpendCapExceeded as exc:
        if email.classification is not None:
            return _detail(email, notice=f"{exc} Showing the stored analysis.")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return _detail(email)
