from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Order
from app.services.decisions import DecisionError, decision_options, record_decision

router = APIRouter(prefix="/orders/{order_id}", tags=["decisions"])


class DecisionIn(BaseModel):
    # as_requested | full_by_earliest | split
    choice: str
    decided_by: str = Field(min_length=1, max_length=100)


def _order(session: Session, order_id: int) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return order


@router.get("/decision-options")
def options(order_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """What the buyer can accept: the order as requested, plus the plans the reply proposed."""
    return decision_options(session, _order(session, order_id))


@router.post("/decision")
def decide(order_id: int, payload: DecisionIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Record the buyer's choice: adds an internal PO version with that plan and confirms the order."""
    order = _order(session, order_id)
    try:
        version = record_decision(session, order, payload.choice, payload.decided_by)
    except DecisionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"order_id": order.id, "status": order.status, "version": version.version,
            "shipments": version.data.get("shipments", [])}
