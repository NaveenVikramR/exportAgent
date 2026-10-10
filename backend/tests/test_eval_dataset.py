"""The eval labels are hand-written; these checks catch typos in them."""

from datetime import date
from decimal import Decimal

import pytest

from app.schemas.extraction import SCALAR_FIELDS, EmailCategory
from eval.dataset import load_cases, load_expected
from eval.scoring import values_match

CASES = load_cases("dev") + load_cases("test")
CATEGORIES = {category.value for category in EmailCategory}


def test_case_ids_are_unique():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids)) >= 10


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_label_is_well_formed(case):
    expected = load_expected(case.id)
    assert expected["id"] == case.id

    classification = expected["classification"]
    assert classification["category"] in CATEGORIES
    assert set(classification["intents"]) <= CATEGORIES
    assert classification["category"] in classification["intents"]

    extraction = expected["extraction"]
    assert (extraction is not None) == classification["has_po_data"]
    review_fields = set(expected.get("expected_review_fields") or [])
    assert review_fields <= set(SCALAR_FIELDS)
    assert set(expected.get("skip_fields") or []) <= set(SCALAR_FIELDS)
    if extraction is None:
        return

    assert set(extraction) == set(SCALAR_FIELDS) | {"line_items"}
    if extraction["delivery_date"]:
        date.fromisoformat(extraction["delivery_date"])
    if extraction["unit_price"]:
        Decimal(extraction["unit_price"])
    for item in extraction["line_items"]:
        if item.get("sizes"):
            assert sum(item["sizes"].values()) == item["quantity"]
    if extraction["line_items"] and extraction["total_quantity"]:
        assert sum(item["quantity"] for item in extraction["line_items"]) == extraction["total_quantity"]


@pytest.mark.parametrize(
    ("name", "expected", "actual", "match"),
    [
        ("buyer", "Bluepeak Outfitters Inc.", "BLUEPEAK OUTFITTERS INC", True),
        ("buyer", "Nordwind Mode GmbH", "Nordwind", False),
        ("unit_price", "6.40", Decimal("6.4"), True),
        ("unit_price", "6.40", Decimal("6.45"), False),
        ("total_quantity", 12000, 12000, True),
        ("delivery_date", "2027-01-05", date(2027, 1, 5), True),
        ("delivery_date", "2027-01-05", date(2027, 5, 1), False),
        ("currency", None, None, True),
        ("currency", None, "USD", False),
        ("po_number", "BP-778301", None, False),
    ],
)
def test_values_match(name, expected, actual, match):
    assert values_match(name, expected, actual) is match


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_risk_label_uses_known_groups(case):
    expected = load_expected(case.id)

    assert set(expected["expected_high_risk"]) <= {"schedule", "value"}
    if expected["extraction"] is None:
        assert expected["expected_high_risk"] == []
