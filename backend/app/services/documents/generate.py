"""Generates the Commercial Invoice and Packing List PDFs for a confirmed order."""

import json
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.models import Document, Order
from app.services.documents.compute import build_invoice, build_packing_list, split_shipments
from app.services.documents.render import render_invoice, render_packing_list
from app.services.profiles import load_profile

GENERATED_DIR = BACKEND_DIR / "generated" / "documents"


class DocumentError(RuntimeError):
    """Documents cannot be generated for this order yet."""


def _plain(value: Any) -> Any:
    """JSON-safe copy (Decimals as strings)."""
    return json.loads(json.dumps(value, default=str))


def generate_documents(session: Session, order: Order, *, on: date | None = None) -> list[Document]:
    if order.status != "confirmed":
        raise DocumentError(
            "Documents are generated for confirmed orders only: approve the reply to the buyer, and if it proposed "
            "alternatives, record the buyer's decision."
        )
    if not order.versions:
        raise DocumentError("The order has no PO data.")
    on = on or datetime.now(UTC).date()
    version = order.versions[-1]
    profile = load_profile(order.profile)

    folder = GENERATED_DIR / str(order.id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    documents = []
    # One invoice and packing list per agreed shipment.
    pairs = []
    for shipment in split_shipments(version.data):
        invoice = build_invoice(order, shipment, version.version, profile, on)
        packing = build_packing_list(order, shipment, version.version, profile, on, invoice.number)
        suffix = f"-s{shipment['shipment']['index']}" if shipment.get("shipment") else ""
        pairs += [("commercial_invoice", invoice, render_invoice(invoice), suffix),
                  ("packing_list", packing, render_packing_list(packing), suffix)]
    for kind, content, pdf, suffix in pairs:
        path = folder / f"{kind}-v{version.version}{suffix}-{stamp}.pdf"
        path.write_bytes(pdf)
        document = Document(
            order_id=order.id, po_version=version.version, kind=kind, number=content.number,
            profile=profile.id, path=str(path), data=_plain(content.to_dict()), tbc_fields=content.tbc_fields,
        )
        session.add(document)
        documents.append(document)
    session.commit()
    return documents
