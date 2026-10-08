"""The order store. Every PO version is kept; nothing is overwritten."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.tools.diff_po_versions import (
    confidence_from_extraction,
    plan_versions,
    snapshot_from_extraction,
)
from app.config import get_settings
from app.models import Email, Order, POVersion
from app.schemas.extraction import POExtraction
from app.schemas.orders import StatedChange


def normalise_po_number(po_number: str) -> str:
    return "".join(po_number.split()).casefold()


def find_order(session: Session, po_number: str) -> Order | None:
    """PO numbers are the matching key; spacing and case are ignored."""
    key = normalise_po_number(po_number)
    return session.scalar(
        select(Order).where(func.lower(func.replace(Order.po_number, " ", "")) == key)
    )


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


def record_po_version(
    session: Session,
    email: Email,
    extraction: POExtraction,
    stated_changes: list[StatedChange],
) -> POVersion | None:
    """Match the email to an order by PO number and append versions (see plan_versions).

    Returns the email's version, or None when there is no PO number to match on
    or nothing changed. The same email never adds a second version, so
    re-running analysis is safe.
    """
    po_number = extraction.po_number.value
    if not po_number:
        return None

    existing = session.scalar(select(POVersion).where(POVersion.email_id == email.id))
    if existing is not None:
        email.order_id = existing.order_id
        return existing

    update = snapshot_from_extraction(extraction)
    confidence = confidence_from_extraction(extraction)
    order = find_order(session, po_number)
    if order is None:
        order = Order(
            buyer=update.get("buyer") or "Unknown buyer",
            po_number=po_number,
            style=update.get("style"),
            profile=get_settings().factory_profile,
            current_version=0,
        )
        session.add(order)
    email.order = order

    previous = order.versions[-1].data if order.versions else None
    version = None
    for planned in plan_versions(previous, update, stated_changes):
        version = _add_version(
            session,
            order,
            data=planned.data,
            confidence=confidence if planned.from_email else None,
            changes=planned.changes,
            email_id=email.id if planned.from_email else None,
            basis=planned.basis,
        )
    return version
