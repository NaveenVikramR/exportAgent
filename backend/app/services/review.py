"""Plain-Python checks on an extraction: which fields a human must look at.

The model reports a confidence per field; these rules correct it with things
that can be verified: is the quoted evidence really in the email, does it
contain the value, do the quantities add up, is a required field missing.
"""

import re

from app.schemas.extraction import (
    SCALAR_FIELDS,
    EmailCategory,
    POExtraction,
    ReviewedExtraction,
    ReviewFlag,
)

_UNVERIFIED_CONFIDENCE = 0.4

# A full PO needs every field; a change notice only has to identify the order.
_REQUIRED_BY_CATEGORY: dict[EmailCategory, tuple[str, ...]] = {
    EmailCategory.NEW_PO: SCALAR_FIELDS,
    EmailCategory.PO_REVISION: SCALAR_FIELDS,
}
_REQUIRED_DEFAULT: tuple[str, ...] = ("po_number",)

# Codes are copied, not paraphrased, so the quote must contain the value itself.
_CODE_FIELDS = ("po_number", "style", "currency", "incoterms", "port")
_CURRENCY_SYMBOLS = {"USD": ("$",), "EUR": ("€",), "GBP": ("£",), "AUD": ("$", "a$")}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _evidence_states(name: str, value: str, evidence: str) -> bool:
    quote = _normalise(evidence)
    if _normalise(value) in quote:
        return True
    return name == "currency" and any(symbol in quote for symbol in _CURRENCY_SYMBOLS.get(value.upper(), ()))


def review_extraction(
    extraction: POExtraction,
    source_text: str,
    category: EmailCategory,
    threshold: float,
) -> ReviewedExtraction:
    fields = extraction.model_copy(deep=True)
    flags: list[ReviewFlag] = []
    source = _normalise(source_text)
    required = _REQUIRED_BY_CATEGORY.get(category, _REQUIRED_DEFAULT)

    for name in SCALAR_FIELDS:
        field = getattr(fields, name)
        if field.value is None:
            field.confidence = 0
            if name in required:
                flags.append(ReviewFlag(field=name, reason="missing", detail="Not stated in the email."))
            continue
        if not field.evidence or _normalise(field.evidence) not in source:
            field.confidence = min(field.confidence, _UNVERIFIED_CONFIDENCE)
            flags.append(
                ReviewFlag(
                    field=name,
                    reason="evidence_not_found",
                    detail="The quoted source text does not appear in the email.",
                )
            )
        elif name in _CODE_FIELDS and not _evidence_states(name, str(field.value), field.evidence):
            field.confidence = min(field.confidence, _UNVERIFIED_CONFIDENCE)
            flags.append(
                ReviewFlag(
                    field=name,
                    reason="evidence_mismatch",
                    detail=f"The quoted source text does not contain {field.value}.",
                )
            )

    # A line without a stated quantity still counts with its size breakdown.
    item_quantities = [
        item.quantity if item.quantity is not None else sum(item.sizes.values())
        for item in fields.line_items
        if item.quantity is not None or item.sizes
    ]
    for item in fields.line_items:
        if item.sizes and item.quantity is not None and sum(item.sizes.values()) != item.quantity:
            flags.append(
                ReviewFlag(
                    field="line_items",
                    reason="quantity_mismatch",
                    detail=(
                        f"{item.colour}: sizes add up to {sum(item.sizes.values())}, "
                        f"line total says {item.quantity}."
                    ),
                )
            )
    total = fields.total_quantity
    if total.value is not None and item_quantities and sum(item_quantities) != total.value:
        total.confidence = min(total.confidence, _UNVERIFIED_CONFIDENCE)
        flags.append(
            ReviewFlag(
                field="total_quantity",
                reason="quantity_mismatch",
                detail=f"Line items add up to {sum(item_quantities)}, total says {total.value}.",
            )
        )

    already_flagged = {flag.field for flag in flags}
    for name in SCALAR_FIELDS:
        field = getattr(fields, name)
        if field.value is not None and field.confidence < threshold and name not in already_flagged:
            flags.append(
                ReviewFlag(
                    field=name,
                    reason="low_confidence",
                    detail=f"Confidence {field.confidence:.2f} is below {threshold:.2f}.",
                )
            )

    return ReviewedExtraction(fields=fields, review=flags)
