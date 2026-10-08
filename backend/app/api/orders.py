from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Order
from app.schemas.orders import OrderDetail, OrderSummary, POVersionOut

router = APIRouter(prefix="/orders", tags=["orders"])


def _latest_changes(order: Order) -> list[dict]:
    return (order.versions[-1].changes or []) if order.versions else []


def _summary_fields(order: Order) -> dict:
    changes = _latest_changes(order)
    return {
        "alerts": sorted({change["alert"] for change in changes if change.get("alert")}),
        "latest_change_count": len(changes),
    }


@router.get("", response_model=list[OrderSummary])
def list_orders(session: Session = Depends(get_session)) -> list[OrderSummary]:
    orders = session.scalars(select(Order).order_by(Order.updated_at.desc(), Order.id.desc()))
    return [
        OrderSummary.model_validate(order).model_copy(update=_summary_fields(order))
        for order in orders
    ]


@router.get("/{order_id}", response_model=OrderDetail)
def get_order(order_id: int, session: Session = Depends(get_session)) -> OrderDetail:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    summary = OrderSummary.model_validate(order).model_copy(update=_summary_fields(order))
    return OrderDetail(
        **summary.model_dump(),
        versions=[POVersionOut.model_validate(version) for version in reversed(order.versions)],
    )
