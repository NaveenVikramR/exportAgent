from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChangeKind = Literal["quantity", "price", "delivery_date", "size_ratio", "colour", "incoterms", "other"]

# The change an exporter most needs to see: less time to produce the same order.
DELIVERY_PULLED_FORWARD = "delivery_pulled_forward"


class Change(BaseModel):
    # "delivery_date", or "line_items.<colour>.quantity" / ".sizes" / ".unit_price", or "line_items.<colour>"
    field: str
    kind: ChangeKind
    old: Any = None
    new: Any = None
    detail: str
    alert: str | None = None


StatedField = Literal[
    "buyer", "style", "currency", "unit_price", "total_quantity",
    "delivery_date", "incoterms", "port", "destination_country",
]


class StatedChange(BaseModel):
    """A change the email itself spells out, e.g. "we now need 10 Nov instead of 24 Nov"."""

    field: StatedField
    old: str | int | float | None = None
    new: str | int | float | None = None
    evidence: str | None = None


class StatedChanges(BaseModel):
    changes: list[StatedChange] = Field(default_factory=list)


class POVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    email_id: int | None
    # document: from a PO or order email; thread_reference: earlier values quoted in a reply thread
    basis: str
    data: dict[str, Any]
    confidence: dict[str, Any] | None
    changes: list[Change] | None
    created_at: datetime


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    buyer: str
    po_number: str
    style: str | None
    status: str
    profile: str
    current_version: int
    updated_at: datetime
    # alerts raised by the latest version's changes
    alerts: list[str] = Field(default_factory=list)
    latest_change_count: int = 0


class OrderDetail(OrderSummary):
    versions: list[POVersionOut]
