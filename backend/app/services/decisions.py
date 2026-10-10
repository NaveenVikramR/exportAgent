"""Order states after the reply, and the buyer's decision on a proposed plan.

open            -> a PO version arrived and nobody has replied yet
awaiting_buyer  -> the approved reply proposed alternatives (a later date or a split)
confirmed       -> the buyer accepted a plan; documents can be generated

Recording the buyer's decision adds an internal PO version (basis "buyer_decision")
with the accepted shipment plan, so the order history shows what was agreed.
"""

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tools.diff_po_versions import diff_po_versions
from app.models import AgentRun, AgentStep, Order, POVersion
from app.schemas.orders import Change

OPEN, AWAITING_BUYER, CONFIRMED = "open", "awaiting_buyer", "confirmed"


class DecisionError(RuntimeError):
    """The decision cannot be recorded (unknown option, no order data)."""


def proposed_options(session: Session, order: Order) -> dict[str, Any] | None:
    """The delivery options from the order's latest risk assessment, if alternatives were proposed."""
    step = session.scalar(
        select(AgentStep)
        .join(AgentRun, AgentStep.run_id == AgentRun.id)
        .where(AgentRun.order_id == order.id, AgentStep.name == "propose_delivery_options")
        .order_by(AgentStep.id.desc())
        .limit(1)
    )
    output = step.output if step is not None else None
    if not output or not output.get("options_needed"):
        return None
    current = order.versions[-1].data if order.versions else {}
    # Options computed for an older plan no longer apply.
    if output.get("requested_date") != current.get("delivery_date") or output.get("quantity") != current.get("total_quantity"):
        return None
    return output


def status_after_reply(session: Session, order: Order) -> str:
    """An approved reply confirms the order, unless it proposed alternatives the buyer must choose from."""
    return AWAITING_BUYER if proposed_options(session, order) else CONFIRMED


def decision_options(session: Session, order: Order) -> list[dict[str, Any]]:
    if not order.versions:
        return []
    current = order.versions[-1].data
    quantity, requested = current.get("total_quantity"), current.get("delivery_date")
    options = []
    if quantity and requested:
        options.append({
            "id": "as_requested",
            "label": f"Accepted as requested: {quantity:,} pcs by {requested}",
            "shipments": [{"quantity": quantity, "delivery_date": requested}],
        })
    proposed = proposed_options(session, order)
    if proposed:
        earliest = proposed.get("earliest_feasible_date_full_quantity")
        if earliest:
            options.append({
                "id": "full_by_earliest",
                "label": f"Full quantity later: {quantity:,} pcs by {earliest}",
                "shipments": [{"quantity": quantity, "delivery_date": earliest}],
            })
        split = proposed.get("partial_shipment")
        if split and split.get("balance_date"):
            options.append({
                "id": "split",
                "label": (f"Split shipment: {split['quantity_on_requested_date']:,} pcs by {split['requested_date']}, "
                          f"{split['balance_quantity']:,} pcs by {split['balance_date']}"),
                "shipments": [
                    {"quantity": split["quantity_on_requested_date"], "delivery_date": split["requested_date"]},
                    {"quantity": split["balance_quantity"], "delivery_date": split["balance_date"]},
                ],
            })
    return options


def record_decision(session: Session, order: Order, choice: str, decided_by: str) -> POVersion:
    option = next((o for o in decision_options(session, order) if o["id"] == choice), None)
    if option is None:
        raise DecisionError(f"'{choice}' is not one of the options for this order.")
    current = order.versions[-1].data
    data = deepcopy(current)
    data["shipments"] = option["shipments"]
    data["delivery_date"] = option["shipments"][-1]["delivery_date"]
    changes = diff_po_versions(current, data) + [
        Change(field="buyer_decision", kind="other", old=None, new=option["label"],
               detail=f"Buyer decision recorded by {decided_by}: {option['label']}."),
    ]
    version = POVersion(
        order=order, version=order.current_version + 1, email_id=None, basis="buyer_decision",
        data=data, confidence=None, changes=[c.model_dump(mode="json") for c in changes],
    )
    session.add(version)
    order.current_version = version.version
    order.status = CONFIRMED
    session.commit()
    return version
