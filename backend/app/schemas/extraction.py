from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

T = TypeVar("T")


class EmailCategory(StrEnum):
    NEW_PO = "new_po"
    PO_REVISION = "po_revision"
    DELIVERY_CHANGE = "delivery_change"
    ORDER_QUERY = "order_query"
    SAMPLE_OR_APPROVAL = "sample_or_approval"
    SHIPMENT_DOCS = "shipment_docs"
    PAYMENT = "payment"
    OTHER = "other"


class Classification(BaseModel):
    # the main request; `intents` lists every request in the email, including this one
    category: EmailCategory
    intents: list[EmailCategory] = Field(default_factory=list)
    has_po_data: bool
    summary: str
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _category_is_an_intent(self) -> "Classification":
        if self.category not in self.intents:
            self.intents.insert(0, self.category)
        self.intents = list(dict.fromkeys(self.intents))
        return self


class Extracted(BaseModel, Generic[T]):
    """One extracted value with the model's confidence and the source text it came from."""

    value: T | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: str | None = None


class LineItem(BaseModel):
    colour: str | None = None
    sizes: dict[str, int] = Field(default_factory=dict)
    quantity: int | None = None
    unit_price: Decimal | None = None


class POExtraction(BaseModel):
    buyer: Extracted[str] = Field(default_factory=Extracted[str])
    po_number: Extracted[str] = Field(default_factory=Extracted[str])
    style: Extracted[str] = Field(default_factory=Extracted[str])
    currency: Extracted[str] = Field(default_factory=Extracted[str])
    unit_price: Extracted[Decimal] = Field(default_factory=Extracted[Decimal])
    total_quantity: Extracted[int] = Field(default_factory=Extracted[int])
    delivery_date: Extracted[date] = Field(default_factory=Extracted[date])
    incoterms: Extracted[str] = Field(default_factory=Extracted[str])
    port: Extracted[str] = Field(default_factory=Extracted[str])
    destination_country: Extracted[str] = Field(default_factory=Extracted[str])
    line_items: list[LineItem] = Field(default_factory=list)

    @field_validator("currency", "incoterms")
    @classmethod
    def _upper(cls, field: Extracted[str]) -> Extracted[str]:
        if field.value:
            field.value = field.value.strip().upper()
        return field

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, field: Extracted[str]) -> Extracted[str]:
        if field.value and not (len(field.value) == 3 and field.value.isalpha()):
            raise ValueError("currency must be a 3-letter ISO 4217 code such as USD")
        return field


SCALAR_FIELDS: tuple[str, ...] = (
    "buyer",
    "po_number",
    "style",
    "currency",
    "unit_price",
    "total_quantity",
    "delivery_date",
    "incoterms",
    "port",
    "destination_country",
)


class ReviewFlag(BaseModel):
    field: str
    # missing | low_confidence | evidence_not_found | quantity_mismatch
    reason: str
    detail: str


class ReviewedExtraction(BaseModel):
    fields: POExtraction
    review: list[ReviewFlag] = Field(default_factory=list)
