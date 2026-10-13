"""The order store. Every PO version is kept; nothing is overwritten.

An email is matched to an order with a scored match (app/services/order_matching.py):
confident matches are applied, uncertain ones are put to a person ("Is this a revision
of PO X?"), and an order can exist before its PO number is known.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tools.diff_po_versions import (
    confidence_from_extraction,
    plan_versions,
    snapshot_from_extraction,
)
from app.config import get_settings
from app.models import Email, Order, POVersion
from app.schemas.extraction import POExtraction, ReviewedExtraction
from app.schemas.orders import StatedChange
from app.services.normalise import removed_colours, split_letter_suffix
from app.services.order_matching import MatchResult, match_order, po_key
from app.services.review import inherit_from_previous


def normalise_po_number(po_number: str) -> str:
    """The comparable form of a PO number (revision suffix, spacing and case ignored)."""
    return po_key(po_number) or ""


def find_order(session: Session, po_number: str) -> Order | None:
    """The order with this PO number; a revision suffix, spacing and case are ignored."""
    key = po_key(po_number)
    return next((o for o in session.scalars(select(Order)) if key and po_key(o.po_number) == key), None)


def _add_version(
    session: Session,
    order: Order,
    *,
    data: dict,
    confidence: dict | None,
    changes: list,
    email_id: int | None,
    basis: str,
) -> POVersion:
    version = POVersion(
        order=order,
        version=order.current_version + 1,
        email_id=email_id,
        basis=basis,
        data=data,
        confidence=confidence,
        changes=[change.model_dump(mode="json") for change in changes],
    )
    session.add(version)
    order.current_version = version.version
    order.style = data.get("style") or order.style
    return version


@dataclass
class RecordResult:
    version: POVersion | None = None
    order: Order | None = None
    # the order's data before this email (None for a new order)
    previous: dict | None = None
    match: MatchResult | None = None
    # True when a person has to confirm which order this is
    asked: bool = False


def _new_order(session: Session, update: dict) -> Order:
    order = Order(
        buyer=update.get("buyer") or "Unknown buyer",
        po_number=update.get("po_number"),
        style=update.get("style"),
        profile=get_settings().factory_profile,
        current_version=0,
    )
    session.add(order)
    return order


def record_email_po(
    session: Session,
    email: Email,
    extraction: POExtraction,
    stated_changes: list[StatedChange],
    text: str,
    *,
    force_order: Order | None = None,
    force_new: bool = False,
) -> RecordResult:
    """Match the email to an order and append versions (see plan_versions).

    - confident match: versions are added to that order;
    - uncertain match: nothing is recorded; the question is stored on the email for a person;
    - no match: a new order (with or without a PO number) is created.
    The same email never adds a second version, so re-running analysis is safe.
    """
    existing = session.scalar(select(POVersion).where(POVersion.email_id == email.id))
    if existing is not None:
        email.order_id = existing.order_id
        return RecordResult(version=existing, order=existing.order)

    _read_letter_revision(session, extraction)
    update = snapshot_from_extraction(extraction)
    if extraction.po_revision:
        update["po_revision"] = extraction.po_revision
    match = None
    if force_order is not None:
        order = force_order
    elif force_new:
        order = _new_order(session, update)
    else:
        match = match_order(session, update, text)
        if match.decision == "ask":
            email.match = {
                "candidate_order_id": match.best.order.id,
                "candidate_po_number": match.best.order.po_number,
                "candidate_buyer": match.best.order.buyer,
                "score": match.best.score,
                "reasons": match.best.reasons,
                "stated_changes": [c.model_dump(mode="json") for c in stated_changes],
                "status": "pending",
            }
            return RecordResult(match=match, asked=True)
        order = match.order if match.decision == "match" else _new_order(session, update)

    style = update.get("style")
    if not update.get("po_number") and order.po_number and style and po_key(style) == po_key(order.po_number):
        # The email names the order by its PO number without saying "PO"; it was read as the style.
        update["po_number"], update["style"] = order.po_number, None
        extraction.po_number, extraction.style = extraction.style, extraction.po_number
    if order.po_number is None and update.get("po_number"):
        # The PO number arrived after the order: record it.
        order.po_number = update["po_number"]
    email.order = order

    previous = order.versions[-1].data if order.versions else None
    if previous is not None and not previous.get("po_number") and order.po_number:
        # A PO number that arrived with no other change is on the order, not in a version yet.
        previous = {**previous, "po_number": order.po_number}
    if previous is not None and text:
        _mark_removed_colours(update, previous, text)
    version = None
    planned_versions = plan_versions(previous, update, stated_changes)
    if planned_versions:
        # New PO data: whatever was agreed before has to be agreed again.
        order.status = "open"
    for planned in planned_versions:
        version = _add_version(
            session,
            order,
            data=planned.data,
            confidence=confidence_from_extraction(extraction) if planned.from_email else None,
            changes=planned.changes,
            email_id=email.id if planned.from_email else None,
            basis=planned.basis,
        )
    return RecordResult(version=version, order=order, previous=previous, match=match)


def _read_letter_revision(session: Session, extraction: POExtraction) -> None:
    """"PRN-2210-A" is revision A of PRN-2210 when PRN-2210 is a known order and PRN-2210-A is not."""
    po = extraction.po_number.value
    if not po or extraction.po_revision or find_order(session, po) is not None:
        return
    base, letter = split_letter_suffix(po)
    if letter and find_order(session, base) is not None:
        extraction.po_number.value, extraction.po_revision = base, letter


def _mark_removed_colours(update: dict, previous: dict, text: str) -> None:
    """Colours the email drops or cancels go into the update with quantity 0 (removed on merge)."""
    colours = [item["colour"] for item in previous.get("line_items") or [] if item.get("colour")]
    items = update.setdefault("line_items", [])
    named = {(item.get("colour") or "").casefold(): item for item in items}
    for colour in removed_colours(text, colours):
        if colour.casefold() in named:
            named[colour.casefold()]["quantity"] = 0
            named[colour.casefold()]["sizes"] = {}
        else:
            items.append({"colour": colour, "quantity": 0, "sizes": {}, "unit_price": None})


def record_po_version(
    session: Session,
    email: Email,
    extraction: POExtraction,
    stated_changes: list[StatedChange],
    text: str = "",
) -> POVersion | None:
    """record_email_po, returning only the email's version."""
    return record_email_po(session, email, extraction, stated_changes, text).version


def resolve_match(session: Session, email: Email, same_order: bool, decided_by: str) -> RecordResult:
    """A person answered "Is this a revision of PO X?"; record the email accordingly."""
    pending = email.match or {}
    if pending.get("status") != "pending":
        raise ValueError("This email has no open order-match question.")
    extraction = POExtraction.model_validate((email.extraction or {}).get("fields") or {})
    stated = [StatedChange.model_validate(c) for c in pending.get("stated_changes", [])]
    order = session.get(Order, pending["candidate_order_id"]) if same_order else None
    result = record_email_po(session, email, extraction, stated, "", force_order=order, force_new=not same_order)
    if result.previous and email.extraction:
        # Fields the email did not restate come from the order, as for a confident match.
        reviewed = ReviewedExtraction.model_validate(email.extraction)
        inherit_from_previous(reviewed, result.previous)
        email.extraction = reviewed.model_dump(mode="json")
        if not reviewed.review:
            email.status = "analysed"
    email.match = {**pending, "status": "answered", "same_order": same_order, "decided_by": decided_by}
    session.commit()
    return result


def match_question(email: Email) -> dict[str, Any] | None:
    pending = email.match or {}
    if pending.get("status") != "pending":
        return None
    po = pending.get("candidate_po_number") or "(PO number pending)"
    return {
        "email_id": email.id,
        "question": f"Is this email about the existing order PO {po} from {pending.get('candidate_buyer')}?",
        "score": pending.get("score"),
        "reasons": pending.get("reasons", []),
        "candidate_order_id": pending.get("candidate_order_id"),
    }
