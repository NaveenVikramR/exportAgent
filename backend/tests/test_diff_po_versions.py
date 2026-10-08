from copy import deepcopy

import pytest

from app.agent.tools.diff_po_versions import (
    apply_stated_changes,
    diff_po_versions,
    merge_snapshots,
    plan_versions,
)
from app.schemas.orders import DELIVERY_PULLED_FORWARD, StatedChange
from eval.dataset import load_expected
from eval.scoring import score_changes


def _label_snapshot(case_id: str) -> dict:
    """A labelled extraction in snapshot form."""
    data = deepcopy(load_expected(case_id)["extraction"])
    for item in data["line_items"]:
        item.setdefault("sizes", {})
        item.setdefault("unit_price", None)
    return data


def _keys(changes) -> set[str]:
    return {change.field for change in changes}


# --- The labelled cases -----------------------------------------------------------


@pytest.mark.parametrize(("original", "revision"), [("case_001", "case_002"), ("case_005", "case_009")])
def test_revised_po_matches_labelled_changes(original, revision):
    expected = load_expected(revision)["expected_changes"]

    changes = diff_po_versions(_label_snapshot(original), _label_snapshot(revision))

    score = score_changes(revision, expected, changes)
    assert (score.correct, score.predicted) == (len(expected), len(expected)), (score.missed, score.unexpected)


def test_reply_thread_change_matches_label():
    expected = load_expected("case_007")["expected_changes"]
    current = _label_snapshot("case_007")
    stated = [StatedChange(field="delivery_date", old="2026-11-24", new="2026-11-10")]

    versions = plan_versions(None, current, stated)

    assert [v.basis for v in versions] == ["thread_reference", "document"]
    assert versions[0].data["delivery_date"] == "2026-11-24"
    score = score_changes("case_007", expected, versions[1].changes)
    assert (score.correct, score.predicted) == (1, 1)
    assert versions[1].changes[0].alert == DELIVERY_PULLED_FORWARD


def test_case_002_flags_the_pulled_forward_delivery():
    changes = diff_po_versions(_label_snapshot("case_001"), _label_snapshot("case_002"))

    delivery = next(change for change in changes if change.field == "delivery_date")
    assert delivery.alert == DELIVERY_PULLED_FORWARD
    assert "15 days" in delivery.detail


def test_scaling_a_colour_keeps_its_size_ratio():
    # case_002 Navy goes 600/1500/1500/900 -> 800/2000/2000/1200: same 2:5:5:3 ratio
    changes = diff_po_versions(_label_snapshot("case_001"), _label_snapshot("case_002"))

    assert "line_items.Navy.sizes" not in _keys(changes)
    assert "line_items.Navy.quantity" in _keys(changes)


# --- Each kind of change ---------------------------------------------------------------


def _base(**overrides) -> dict:
    snapshot = {
        "buyer": "Acme Ltd", "po_number": "AB-1", "style": "ST-1", "currency": "USD",
        "unit_price": "4.00", "total_quantity": 1000, "delivery_date": "2026-12-15",
        "incoterms": "FOB", "port": "Chennai", "destination_country": "Germany",
        "line_items": [
            {"colour": "Navy", "sizes": {"S": 200, "M": 300}, "quantity": 500, "unit_price": None},
            {"colour": "White", "sizes": {"S": 200, "M": 300}, "quantity": 500, "unit_price": None},
        ],
    }
    snapshot.update(overrides)
    return snapshot


def test_identical_versions_have_no_changes():
    assert diff_po_versions(_base(), _base()) == []


def test_price_change():
    [change] = diff_po_versions(_base(), _base(unit_price="3.80"))

    assert (change.field, change.kind, change.old, change.new) == ("unit_price", "price", "4.00", "3.80")


def test_equal_prices_written_differently_are_not_a_change():
    assert diff_po_versions(_base(unit_price="4.00"), _base(unit_price="4.0")) == []


def test_delivery_pushed_back_is_not_flagged():
    [change] = diff_po_versions(_base(), _base(delivery_date="2027-01-10"))

    assert change.alert is None
    assert "pushed back by 26 days" in change.detail


def test_delivery_pulled_forward_is_flagged():
    [change] = diff_po_versions(_base(), _base(delivery_date="2026-12-01"))

    assert change.kind == "delivery_date"
    assert change.alert == DELIVERY_PULLED_FORWARD
    assert "14 days" in change.detail


def test_incoterm_and_port_changes():
    changes = diff_po_versions(_base(), _base(incoterms="CIF", port="Le Havre"))

    assert {(c.field, c.kind, c.old, c.new) for c in changes} == {
        ("incoterms", "incoterms", "FOB", "CIF"),
        ("port", "incoterms", "Chennai", "Le Havre"),
    }


def test_quantity_change_detail_shows_delta():
    [change] = diff_po_versions(_base(), _base(total_quantity=1200))

    assert change.kind == "quantity"
    assert change.detail == "Total quantity 1,000 → 1,200 pcs, +200 (+20.0%)."


def test_line_prices_repeating_the_order_price_change_are_not_listed_again():
    old, new = _base(), _base(unit_price="3.80")
    for item in old["line_items"]:
        item["unit_price"] = "4.00"
    for item in new["line_items"]:
        item["unit_price"] = "3.80"

    assert _keys(diff_po_versions(old, new)) == {"unit_price"}


def test_line_price_change_for_one_colour_is_listed():
    old, new = _base(), _base()
    old["line_items"][0]["unit_price"] = "4.00"
    new["line_items"][0]["unit_price"] = "4.20"

    [change] = diff_po_versions(old, new)

    assert (change.field, change.kind) == ("line_items.Navy.unit_price", "price")


def test_size_ratio_change():
    new = _base()
    new["line_items"][0]["sizes"] = {"S": 100, "M": 400}

    [change] = diff_po_versions(_base(), new)

    assert (change.field, change.kind) == ("line_items.Navy.sizes", "size_ratio")
    assert change.old == {"S": 200, "M": 300}
    assert change.new == {"S": 100, "M": 400}


def test_size_breakdown_stated_for_the_first_time_is_not_a_ratio_change():
    old = _base()
    old["line_items"][0]["sizes"] = {}

    assert diff_po_versions(old, _base()) == []


def test_colour_added_and_removed():
    new = _base()
    new["line_items"] = [
        new["line_items"][0],
        {"colour": "Red", "sizes": {}, "quantity": 500, "unit_price": None},
    ]

    changes = {c.field: c for c in diff_po_versions(_base(), new)}

    assert changes["line_items.Red"].kind == "colour"
    assert (changes["line_items.Red"].old, changes["line_items.Red"].new) == (None, 500)
    assert (changes["line_items.White"].old, changes["line_items.White"].new) == (500, None)


def test_colour_names_match_ignoring_case():
    new = _base()
    new["line_items"][0]["colour"] = "NAVY"

    assert diff_po_versions(_base(), new) == []


def test_value_missing_from_the_update_is_unchanged_not_removed():
    update = {name: None for name in _base()} | {"po_number": "AB-1", "delivery_date": "2026-12-01", "line_items": []}

    changes = diff_po_versions(_base(), update)

    assert _keys(changes) == {"delivery_date"}


def test_merge_keeps_unstated_values():
    update = {"po_number": "AB-1", "delivery_date": "2026-12-01", "unit_price": None, "line_items": []}

    merged = merge_snapshots(_base(), update)

    assert merged["delivery_date"] == "2026-12-01"
    assert merged["unit_price"] == "4.00"
    assert len(merged["line_items"]) == 2


def test_stated_changes_with_unparseable_values_are_ignored():
    baseline = apply_stated_changes(
        _base(), [StatedChange(field="delivery_date", old="sometime in November", new="2026-12-15")]
    )

    assert baseline == _base()


def test_plan_for_existing_order_without_changes_is_empty():
    assert plan_versions(_base(), _base(), []) == []


def test_plan_for_new_order_without_stated_changes_is_one_version():
    [version] = plan_versions(None, _base(), [])

    assert (version.basis, version.changes, version.from_email) == ("document", [], True)
