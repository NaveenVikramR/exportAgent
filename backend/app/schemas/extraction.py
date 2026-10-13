from datetime import date
from decimal import Decimal
from enum import StrEnum
import re
from typing import Any, Generic, TypeVar

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


_CATEGORY_VALUES = {c.value for c in EmailCategory}


class Classification(BaseModel):
    # the main request; `intents` lists every request in the email, including this one
    category: EmailCategory
    intents: list[EmailCategory] = Field(default_factory=list)
    has_po_data: bool
    summary: str
    confidence: float = Field(ge=0, le=1)
    # values the model gave outside the allowed list, mapped to "other" (set by Python, not the model)
    unrecognised: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _map_unknown_to_other(cls, data: Any) -> Any:
        """An intent or category outside the enum becomes "other" and is kept for review,
        instead of failing the whole classification."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        unknown = list(data.get("unrecognised") or [])
        category = data.get("category")
        if isinstance(category, str) and category not in _CATEGORY_VALUES:
            unknown.append(category)
            data["category"] = EmailCategory.OTHER.value
        intents = []
        for intent in data.get("intents") or []:
            if isinstance(intent, str) and intent not in _CATEGORY_VALUES:
                unknown.append(intent)
                intent = EmailCategory.OTHER.value
            intents.append(intent)
        data["intents"] = intents
        data["unrecognised"] = list(dict.fromkeys(unknown))
        return data

    @classmethod
    def output_schema(cls) -> dict[str, Any]:
        """JSON schema for the model's reply: the enums constrain category and intents."""
        schema = cls.model_json_schema()
        schema["properties"].pop("unrecognised", None)
        return schema

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


_DECIMAL_COMMA = re.compile(r"^\d{1,3}(?:\.\d{3})+,\d+$|^\d+,\d{1,2}$")
_GROUPED_INT = re.compile(r"^\d{1,3}(?:[.,\s\u00a0\u202f]\d{3})+$")


def _amount(value: Any) -> Any:
    """'9,80' -> '9.80', '41.160,00' -> '41160.00' (European decimal comma)."""
    if isinstance(value, str):
        text = value.strip().replace("\u00a0", "").replace(" ", "")
        if _DECIMAL_COMMA.match(text):
            return text.replace(".", "").replace(",", ".")
    return value


def _count(value: Any) -> Any:
    """'4.200' or '4 200' or '4,200' -> 4200."""
    if isinstance(value, str) and _GROUPED_INT.match(value.strip()):
        return re.sub(r"\D", "", value)
    return value


class LineItem(BaseModel):
    colour: str | None = None
    sizes: dict[str, int] = Field(default_factory=dict)
    quantity: int | None = None
    unit_price: Decimal | None = None

    @field_validator("unit_price", mode="before")
    @classmethod
    def _unit_price(cls, value: Any) -> Any:
        return _amount(value)

    @field_validator("quantity", mode="before")
    @classmethod
    def _quantity(cls, value: Any) -> Any:
        return _count(value)


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
    # revision split off the PO number by app/services/normalise.py ("CL-7731 Rev A" -> "A")
    po_revision: str | None = None
    # fields written as an ambiguous numeric date that could not be resolved (set by normalise.py)
    ambiguous_dates: list[str] = Field(default_factory=list)

    @field_validator("unit_price", "total_quantity", mode="before")
    @classmethod
    def _numbers(cls, field: Any, info) -> Any:
        if isinstance(field, dict) and "value" in field:
            convert = _amount if info.field_name == "unit_price" else _count
            return {**field, "value": convert(field["value"])}
        return field

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
    # missing | low_confidence | evidence_not_found | evidence_mismatch | quantity_mismatch
    reason: str
    detail: str


class Escalation(BaseModel):
    """One field re-extracted by a stronger model after a Python check failed."""

    field: str
    # size_table_not_extracted | size_total_mismatch | source_quote_missing
    reason: str
    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    # resolved: the stronger model's value passed the check and was kept
    # unresolved: it did not, the first value stays and remains flagged
    # failed / skipped_spend_cap: no usable answer
    outcome: str
    before: Any = None
    after: Any = None


class ReviewedExtraction(BaseModel):
    fields: POExtraction
    review: list[ReviewFlag] = Field(default_factory=list)
    escalations: list[Escalation] = Field(default_factory=list)
    # fields the email did not restate, taken from the order's previous version
    inherited: list[str] = Field(default_factory=list)
    # deterministic clean-ups applied (revision suffix split off, colour name restored, ...)
    notes: list[str] = Field(default_factory=list)
