"""Compares one analysis with its label. Pure functions, no I/O."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.extraction import SCALAR_FIELDS
from app.services.analysis import Analysis


@dataclass
class CaseScore:
    case_id: str
    category_ok: bool
    intents_ok: bool
    has_po_data_ok: bool
    # field name -> correct, for the fields that were scored
    fields: dict[str, bool] = field(default_factory=dict)
    line_items_total: int = 0
    line_items_correct: int = 0
    review_expected: set[str] = field(default_factory=set)
    review_flagged: set[str] = field(default_factory=set)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip().rstrip(".").casefold()


def values_match(name: str, expected: Any, actual: Any) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if name == "unit_price":
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    if name == "total_quantity":
        return int(expected) == int(actual)
    return _text(expected) == _text(actual)


def score_case(case_id: str, expected: dict[str, Any], analysis: Analysis) -> CaseScore:
    label = expected["classification"]
    predicted = analysis.classification
    score = CaseScore(
        case_id=case_id,
        category_ok=predicted.category.value == label["category"],
        intents_ok={i.value for i in predicted.intents} == set(label["intents"]),
        has_po_data_ok=predicted.has_po_data == label["has_po_data"],
    )

    expected_fields = expected.get("extraction")
    if expected_fields is None:
        return score

    skip = set(expected.get("skip_fields") or [])
    actual = analysis.extraction.fields if analysis.extraction else None
    for name in SCALAR_FIELDS:
        if name in skip:
            continue
        actual_value = getattr(actual, name).value if actual else None
        score.fields[name] = values_match(name, expected_fields.get(name), actual_value)

    actual_items = {
        _text(item.colour): item for item in (actual.line_items if actual else [])
    }
    for item in expected_fields.get("line_items") or []:
        score.line_items_total += 1
        found = actual_items.get(_text(item["colour"]))
        if found is None or found.quantity != item["quantity"]:
            continue
        # Per-size quantities are only scored where the label writes them out.
        if item.get("sizes") and found.sizes != item["sizes"]:
            continue
        score.line_items_correct += 1

    score.review_expected = set(expected.get("expected_review_fields") or []) - skip
    if analysis.extraction:
        score.review_flagged = {
            flag.field for flag in analysis.extraction.review if flag.field in SCALAR_FIELDS
        } - skip
    return score
