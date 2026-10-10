import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Document, Order
from app.services.documents.generate import DocumentError, generate_documents

router = APIRouter(tags=["documents"])


class DocumentOut(BaseModel):
    id: int
    order_id: int
    po_version: int
    kind: str
    number: str | None
    profile: str | None
    tbc_fields: list[str]
    created_at: datetime
    # headline figures from the computed content
    totals: dict[str, Any]
    download_url: str


def document_out(document: Document) -> DocumentOut:
    data = document.data or {}
    if document.kind == "commercial_invoice":
        totals = {key: data.get(key) for key in ("currency", "total_quantity", "total_amount")}
    else:
        totals = {key: data.get(key) for key in ("total_cartons", "total_quantity", "total_net_kg", "total_gross_kg", "total_cbm")}
    return DocumentOut(
        id=document.id, order_id=document.order_id, po_version=document.po_version, kind=document.kind,
        number=document.number, profile=document.profile, tbc_fields=document.tbc_fields or [],
        created_at=document.created_at, totals=totals, download_url=f"/api/documents/{document.id}/pdf",
    )


def _order_or_404(session: Session, order_id: int) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return order


@router.post("/orders/{order_id}/documents", response_model=list[DocumentOut])
def create(order_id: int, session: Session = Depends(get_session)) -> list[DocumentOut]:
    """Generate the Commercial Invoice and Packing List from the order's latest PO version."""
    try:
        documents = generate_documents(session, _order_or_404(session, order_id))
    except DocumentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return [document_out(d) for d in documents]


@router.get("/orders/{order_id}/documents", response_model=list[DocumentOut])
def list_documents(order_id: int, session: Session = Depends(get_session)) -> list[DocumentOut]:
    _order_or_404(session, order_id)
    documents = session.scalars(select(Document).where(Document.order_id == order_id).order_by(Document.id.desc()))
    return [document_out(d) for d in documents]


@router.get("/documents/{document_id}/pdf")
def download(document_id: int, session: Session = Depends(get_session)) -> FileResponse:
    document = session.get(Document, document_id)
    if document is None or not Path(document.path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{document.kind}_{document.number or document.id}") + ".pdf"
    return FileResponse(document.path, media_type="application/pdf", filename=filename)
