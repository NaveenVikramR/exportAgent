import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.rate_limit import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, SpendCapExceeded, get_router
from app.config import get_settings
from app.models import Email, EmailAttachment
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


class NewEmail(BaseModel):
    sender: str = Field(default="Buyer <buyer@example.com>", max_length=200)
    subject: str = Field(default="(no subject)", max_length=300)
    body: str = Field(min_length=10, max_length=20_000)


def _store(session: Session, sender: str, subject: str, body: str, source: str,
           attachment: EmailAttachment | None = None) -> Email:
    email = Email(sender=sender.strip() or "Buyer <buyer@example.com>", subject=subject.strip() or "(no subject)",
                  body=body, received_at=datetime.now(UTC), source=source,
                  attachments=[attachment] if attachment else [])
    session.add(email)
    session.commit()
    return email


@router.post("", response_model=EmailDetail, dependencies=[Depends(rate_limit)])
def create(payload: NewEmail, session: Session = Depends(get_session)) -> EmailDetail:
    """A pasted email. It is stored as received; analysis runs when asked for."""
    return _detail(_store(session, payload.sender, payload.subject, payload.body, "pasted"))


def pdf_text(data: bytes) -> str:
    """The text layer of a PDF, page by page."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except (PdfReadError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="That file could not be read as a PDF.") from exc


@router.post("/upload", response_model=EmailDetail, dependencies=[Depends(rate_limit)])
async def upload(
    file: UploadFile = File(...),
    sender: str = Form(default="Buyer <buyer@example.com>"),
    subject: str = Form(default=""),
    body: str = Form(default=""),
    session: Session = Depends(get_session),
) -> EmailDetail:
    """A PO as a PDF (with an optional covering email). Only PDFs with a text layer: scans need OCR."""
    data = await file.read(get_settings().upload_max_bytes + 1)
    if len(data) > get_settings().upload_max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="The PDF is larger than 5 MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Please upload a PDF file.")
    text = pdf_text(data)
    if len(text) < 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This PDF has no text layer (probably a scan). Scanned POs are not supported yet; paste the text instead.",
        )
    filename = file.filename or "purchase_order.pdf"
    attachment = EmailAttachment(filename=filename, content_type="application/pdf", text_content=text[:50_000])
    covering = body.strip() or f"Please find our purchase order attached ({filename})."
    return _detail(_store(session, sender, subject or filename.rsplit(".", 1)[0], covering, "upload", attachment))


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
