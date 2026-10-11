"""Classify an email, extract PO fields when it has any, flag what needs review,
and record the result as a version of its order."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agent.tools.classify import classify_email
from app.agent.tools.extract import extract_po_fields
from app.agent.tools.stated_changes import extract_stated_changes
from app.llm.router import LLMError, LLMRouter, SpendCapExceeded
from app.models import Email
from app.schemas.extraction import Classification, EmailCategory, ReviewedExtraction
from app.schemas.orders import StatedChange
from app.services.orders import record_email_po
from app.services.escalation import escalate
from app.services.normalise import normalise_extraction
from app.services.review import inherit_from_previous, review_extraction


@dataclass(frozen=True)
class Analysis:
    classification: Classification
    # final result, after any escalation to the stronger model
    extraction: ReviewedExtraction | None
    # old -> new values the email itself states, e.g. a date changed inside a reply thread
    stated_changes: list[StatedChange] = field(default_factory=list)
    # Nano's result before escalation, kept so the eval can compare
    extraction_before_escalation: ReviewedExtraction | None = None


# Emails that change an existing order may quote its earlier values.
_CHANGE_CATEGORIES = {EmailCategory.DELIVERY_CHANGE, EmailCategory.PO_REVISION}


def render_email_text(
    *,
    sender: str,
    subject: str,
    received_at: str,
    body: str,
    attachments: list[tuple[str, str]],
) -> str:
    """The single text the model sees: headers, body, then each attachment's text."""
    parts = [f"From: {sender}", f"Date: {received_at}", f"Subject: {subject}", "", body.strip()]
    for filename, text in attachments:
        parts += ["", f"--- Attachment: {filename} ---", text.strip()]
    return "\n".join(parts)


def email_text(email: Email) -> str:
    return render_email_text(
        sender=email.sender,
        subject=email.subject,
        received_at=email.received_at.date().isoformat(),
        body=email.body,
        attachments=[(a.filename, a.text_content or "") for a in email.attachments],
    )


# Categories that always concern an order's data, whatever the model said about has_po_data.
_ORDER_CATEGORIES = {EmailCategory.NEW_PO, EmailCategory.PO_REVISION, EmailCategory.DELIVERY_CHANGE}


def analyse_text(router: LLMRouter, text: str) -> Analysis:
    classification = classify_email(router, text)
    if classification.category in _ORDER_CATEGORIES:
        # e.g. "our PO number will follow": still an order, so extract it.
        classification.has_po_data = True
    if not classification.has_po_data:
        return Analysis(classification=classification, extraction=None)
    settings = router.settings
    threshold = settings.review_confidence_threshold
    extraction = extract_po_fields(router, text)
    notes = normalise_extraction(extraction, text)
    reviewed = review_extraction(extraction, text, classification.category, threshold)
    final = (
        escalate(router, reviewed, text, classification.category, threshold)
        if settings.escalation_enabled
        else reviewed
    )
    # Escalated fields (e.g. a re-read PO number or line items) get the same clean-up.
    final.notes = list(dict.fromkeys(notes + normalise_extraction(final.fields, text)))
    stated = (
        extract_stated_changes(router, text)
        if classification.category in _CHANGE_CATEGORIES
        else []
    )
    return Analysis(
        classification=classification,
        extraction=final,
        stated_changes=stated,
        extraction_before_escalation=reviewed,
    )


def analyse_email(session: Session, email: Email, router: LLMRouter) -> Analysis | None:
    """Run the analysis and store it on the email. A failed run never discards an earlier result.

    Returns the analysis, or None when it failed (the error is stored on the email).
    """
    try:
        analysis = analyse_text(router, email_text(email))
    except SpendCapExceeded:
        raise
    except LLMError as exc:
        # Includes replies that failed validation twice: route to a human.
        email.analysis_error = str(exc)
        if email.classification is None:
            email.status = "needs_review"
        session.commit()
        return None

    email.classification = analysis.classification.model_dump(mode="json")
    email.analysis_error = None
    asked = False
    if analysis.extraction:
        recorded = record_email_po(
            session, email, analysis.extraction.fields, analysis.stated_changes, email_text(email)
        )
        asked = recorded.asked
        if recorded.previous:
            inherit_from_previous(analysis.extraction, recorded.previous)
    email.extraction = analysis.extraction.model_dump(mode="json") if analysis.extraction else None
    needs_review = asked or bool(analysis.extraction and analysis.extraction.review)
    email.status = "needs_review" if needs_review else "analysed"
    session.commit()
    return analysis
