import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.agent.tools.diff_po_versions import diff_po_versions, merge_snapshots
from app.db import get_session
from app.llm.router import LLMRouter
from app.main import app
from app.models import Email, Order
from app.schemas.extraction import EmailCategory, POExtraction, ReviewedExtraction, ReviewFlag
from app.services.analysis import analyse_text
from app.services.escalation import has_size_table
from app.services.fact_check import fact_check
from app.services.normalise import normalise_extraction, parse_amount, split_po_revision
from app.services.order_matching import ASK, AUTO_MATCH, match_order
from app.services.orders import record_email_po, resolve_match
from app.services.review import inherit_from_previous
from app.services.risk_policy import contract_value_change, is_high_value_change, load_policy
from tests.scripted import ScriptedClient, reply


# --- PO numbers with revision suffixes --------------------------------------------------------


@pytest.mark.parametrize(("raw", "base", "revision"), [
    ("TL-8812 Rev A", "TL-8812", "A"),
    ("TL-8812-R2", "TL-8812", "2"),
    ("TL-8812 (REV. 3)", "TL-8812", "3"),
    ("KR/2026/114 Amendment 1", "KR/2026/114", "1"),
    ("KR/2026/114", "KR/2026/114", None),
    ("AB-1001-A", "AB-1001-A", None),
    ("PO-R2", "PO-R2", None),
])
def test_split_po_revision(raw, base, revision):
    assert split_po_revision(raw) == (base, revision)


def test_normalise_extraction_splits_the_revision_and_restores_colour_names():
    extraction = POExtraction.model_validate({
        "po_number": {"value": "TL-8812 Rev B", "confidence": 0.9},
        "line_items": [{"colour": "Ocean", "quantity": 800}, {"colour": "Coral Dot", "quantity": 600}],
    })
    text = "Colours: Ocean Stripe 800 pcs, Coral Dot 600 pcs"

    notes = normalise_extraction(extraction, text)

    assert (extraction.po_number.value, extraction.po_revision) == ("TL-8812", "B")
    assert [i.colour for i in extraction.line_items] == ["Ocean Stripe", "Coral Dot"]
    assert len(notes) == 2


# --- decimal commas ---------------------------------------------------------------------------


def test_decimal_comma_amounts_and_grouped_quantities_parse():
    extraction = POExtraction.model_validate({
        "unit_price": {"value": "12,40"}, "total_quantity": {"value": "1.500"},
        "line_items": [{"colour": "Rot", "quantity": "1 500", "unit_price": "12,40"}],
    })

    assert extraction.unit_price.value == Decimal("12.40")
    assert extraction.total_quantity.value == 1500 and extraction.line_items[0].quantity == 1500
    assert parse_amount("18.600,00") == "18600.00" and parse_amount("4.85") == "4.85"


def test_fact_check_reads_decimal_commas():
    facts = {"order": {"unit_price": "12.40", "total_quantity": 1500}}

    assert fact_check("Price EUR 12,40 per piece, total EUR 18.600,00.", facts, "Gesamt: EUR 18.600,00")["violations"] == []
    [violation] = fact_check("Price EUR 12,90 per piece.", facts, "")["violations"]
    assert violation["text"] == "EUR 12,90"


# --- size tables in other languages ---------------------------------------------------------------


@pytest.mark.parametrize("table", [
    "Farbe   S    M    L    XL   Gesamt\nRot     100  200  200  100  600",
    "Coloris / Colour   4A   6A   8A\nRose   300  400  400",
    "Talla | Azul | Rojo\nS | 100 | 120",
    "Kleur/Colour  S  M  L  Totaal\nEcru  250  500  500  1250",
])
def test_size_tables_in_other_languages_are_detected(table):
    assert has_size_table(table)


def test_a_sentence_about_colours_is_not_a_table():
    assert not has_size_table("Colours and quantities: Blanc 2,000 / Marine 2,500\nSize ratio 1:2:3:3:1")


# --- currency-aware value threshold ------------------------------------------------------------


def test_value_threshold_is_converted_to_usd():
    policy = load_policy()
    yen = contract_value_change({"total_quantity": 3400, "unit_price": "520", "currency": "JPY"},
                                {"total_quantity": 3400, "unit_price": "495", "currency": "JPY"})
    dollars = contract_value_change({"total_quantity": 60000, "unit_price": "4.00", "currency": "USD"},
                                    {"total_quantity": 60000, "unit_price": "3.85", "currency": "USD"})

    assert not is_high_value_change(yen, policy)          # -4.8%, about USD 570
    assert is_high_value_change(dollars, policy)          # -3.8% but USD 9,000


# --- partial line-item updates -------------------------------------------------------------------


_ORDER = {"po_number": "SC-1", "total_quantity": 4000, "line_items": [
    {"colour": "White", "sizes": {"8": 300, "10": 500, "12": 500, "14": 200}, "quantity": 1500},
    {"colour": "Black", "sizes": {"8": 300, "10": 500, "12": 500, "14": 200}, "quantity": 1500},
    {"colour": "Sage", "sizes": {}, "quantity": 1000},
]}


def test_partial_update_changes_only_the_named_colour_and_recomputes_the_total():
    update = {"po_number": "SC-1", "total_quantity": None, "line_items": [
        {"colour": "Black", "sizes": {"8": 400, "10": 650, "12": 650, "14": 300}, "quantity": 2000}]}

    merged = merge_snapshots(_ORDER, update)
    changes = {c.field for c in diff_po_versions(_ORDER, merged)}

    assert [i["colour"] for i in merged["line_items"]] == ["White", "Black", "Sage"]
    assert merged["total_quantity"] == 4500
    assert changes == {"total_quantity", "line_items.Black.quantity", "line_items.Black.sizes"}


def test_full_list_with_a_colour_left_out_removes_it():
    update = {"po_number": "SC-1", "total_quantity": 3000, "line_items": [
        {"colour": "White", "quantity": 1500}, {"colour": "Black", "quantity": 1500}]}

    merged = merge_snapshots(_ORDER, update)

    assert [i["colour"] for i in merged["line_items"]] == ["White", "Black"]
    assert "line_items.Sage" in {c.field for c in diff_po_versions(_ORDER, merged)}


# --- field inheritance ----------------------------------------------------------------------------


def test_fields_not_restated_are_inherited_not_flagged():
    reviewed = ReviewedExtraction(fields=POExtraction(), review=[
        ReviewFlag(field="currency", reason="missing", detail="x"),
        ReviewFlag(field="style", reason="missing", detail="x"),
        ReviewFlag(field="unit_price", reason="low_confidence", detail="x"),
    ])

    inherit_from_previous(reviewed, {"currency": "EUR", "style": None, "unit_price": "6.40"})

    assert [(f.field, f.reason) for f in reviewed.review] == [("style", "missing"), ("unit_price", "low_confidence")]
    assert reviewed.inherited == ["currency"]


# --- scored order matching ----------------------------------------------------------------------


def _email(session, subject="x", received="2026-10-01") -> Email:
    email = Email(sender="b@x.example", subject=subject, body="-",
                  received_at=datetime.fromisoformat(received).replace(tzinfo=UTC))
    session.add(email)
    session.flush()
    return email


def _po(**values) -> POExtraction:
    return POExtraction.model_validate(
        {k: {"value": v, "confidence": 0.9, "evidence": str(v)} for k, v in values.items() if k != "line_items"}
        | {"line_items": values.get("line_items", [])}
    )


@pytest.fixture
def store(session_factory):
    with session_factory() as session:
        record_email_po(session, _email(session), _po(po_number="TL-8812", buyer="Tidewater Lane Inc.",
                        style="TL-JK-07", total_quantity=2000, delivery_date="2027-02-20"), [], "")
        record_email_po(session, _email(session), _po(buyer="Orchard Row Ltd", style="OR-SW-40",
                        total_quantity=1800, delivery_date="2027-03-05"), [], "")
        session.commit()
        yield session


def test_revision_suffix_matches_the_order(store):
    extraction = _po(po_number="TL-8812 R2", buyer="Tidewater Lane Inc.", total_quantity=2400)
    normalise_extraction(extraction, "")

    result = record_email_po(store, _email(store), extraction, [], "")

    assert result.order.po_number == "TL-8812" and result.version.version == 2
    assert store.query(Order).count() == 2


def test_po_mentioned_in_the_body_matches_even_if_extracted_as_style(store):
    extraction = _po(style="TL-8812", buyer="Tidewater Lane Inc.", delivery_date="2027-03-06")

    match = match_order(store, {"po_number": None, "style": "TL-8812", "buyer": "Tidewater Lane Inc.",
                                "delivery_date": "2027-03-06"}, "Hi Karthik, TL-8812: please move ex-factory to 6 March.")
    result = record_email_po(store, _email(store), extraction, [], "Hi Karthik, TL-8812: please move ex-factory to 6 March.")

    assert match.decision == "match" and match.best.score >= AUTO_MATCH
    assert result.order.po_number == "TL-8812"


def test_order_without_po_number_matches_by_buyer_style_and_date_and_gets_its_po(store):
    result = record_email_po(store, _email(store), _po(po_number="OR-5521", buyer="Orchard Row Ltd",
                             style="OR-SW-40", delivery_date="2027-03-05"), [], "")

    assert result.order.po_number == "OR-5521"
    assert store.query(Order).count() == 2


def test_uncertain_match_asks_instead_of_creating_a_duplicate(store):
    email = _email(store)
    result = record_email_po(store, email, _po(buyer="Orchard Row Ltd", style="OR-SW-40"), [], "")

    assert result.asked and ASK <= result.match.best.score < AUTO_MATCH
    assert email.match["status"] == "pending" and email.order_id is None
    assert store.query(Order).count() == 2


def test_different_po_number_is_a_different_order(store):
    result = record_email_po(store, _email(store), _po(po_number="TL-9001", buyer="Tidewater Lane Inc.",
                             style="TL-JK-07", delivery_date="2027-02-20"), [], "")

    assert result.order.po_number == "TL-9001" and store.query(Order).count() == 3


def test_match_question_api(session_factory, store):
    email = _email(store)
    email.extraction = {"fields": _po(buyer="Orchard Row Ltd", style="OR-SW-40", unit_price="9.10").model_dump(mode="json")}
    record_email_po(store, email, _po(buyer="Orchard Row Ltd", style="OR-SW-40", unit_price="9.10"), [], "")
    store.commit()

    def override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    try:
        client = TestClient(app)
        [question] = client.get("/api/match-questions").json()
        assert question["email_id"] == email.id and "Orchard Row Ltd" in question["question"]
        answered = client.post(f"/api/emails/{email.id}/match", json={"same_order": True, "decided_by": "Karthik"}).json()
        assert answered["version"] == 2
        assert client.get("/api/match-questions").json() == []
        assert client.post(f"/api/emails/{email.id}/match", json={"same_order": True, "decided_by": "K"}).status_code == 409
    finally:
        app.dependency_overrides.clear()


# --- an email classified as an order is always extracted ---------------------------------------------


def test_order_category_forces_extraction(settings, session_factory):
    classification = {"category": "new_po", "intents": ["new_po"], "has_po_data": False, "summary": "s", "confidence": 0.8}
    extraction = {"buyer": {"value": "Orchard Row Ltd", "confidence": 0.9, "evidence": "Orchard Row Ltd"}}
    router = LLMRouter(settings, client=ScriptedClient([reply(json.dumps(classification)), reply(json.dumps(extraction))]),
                       session_factory=session_factory)

    analysis = analyse_text(router, "Orchard Row Ltd: PO number will follow next week.")

    assert analysis.classification.has_po_data is True
    assert analysis.extraction is not None and analysis.classification.category == EmailCategory.NEW_PO


# --- fixes from the DEV pass after the new cases ---------------------------------------------------


@pytest.mark.parametrize(("raw", "name"), [("USA", "United States"), ("U.K.", "United Kingdom"),
                                           ("España", "Spain"), ("Japan", "Japan")])
def test_country_short_forms_get_one_name(raw, name):
    extraction = _po(destination_country=raw)
    normalise_extraction(extraction, f"Destination: {raw}")
    assert extraction.destination_country.value == name


def test_a_list_of_only_new_colours_adds_to_the_order():
    update = {"po_number": "SC-1", "total_quantity": 300, "line_items": [{"colour": "Heather", "quantity": 300}]}

    merged = merge_snapshots(_ORDER, update)

    assert [i["colour"] for i in merged["line_items"]] == ["White", "Black", "Sage", "Heather"]
    assert merged["total_quantity"] == 4300


def test_buyer_name_variants_are_not_a_change():
    old = {"buyer": "Tidewater Lane Inc.", "line_items": []}
    assert diff_po_versions(old, {"buyer": "TIDEWATER LANE", "line_items": []}) == []


def test_order_reference_read_as_style_becomes_the_po_number(store):
    extraction = _po(style="TL-8812", delivery_date="2027-02-06")

    result = record_email_po(store, _email(store), extraction, [], "Quick one on TL-8812: ex-factory 6 Feb please.")

    assert extraction.po_number.value == "TL-8812" and extraction.style.value is None
    assert {c["field"] for c in result.version.changes} == {"delivery_date"}


def test_answering_yes_inherits_fields_the_email_did_not_restate(store):
    record_email_po(store, _email(store), _po(po_number="OR-5521", buyer="Orchard Row Ltd", style="OR-SW-40",
                    unit_price="8.90", delivery_date="2027-03-05"), [], "")
    email = _email(store)
    extraction = _po(buyer="Orchard Row Ltd", style="OR-SW-40")
    email.extraction = ReviewedExtraction(fields=extraction, review=[
        ReviewFlag(field="po_number", reason="missing", detail="x"),
        ReviewFlag(field="unit_price", reason="missing", detail="x")]).model_dump(mode="json")
    assert record_email_po(store, email, extraction, [], "").asked

    resolve_match(store, email, True, "Karthik")

    reviewed = ReviewedExtraction.model_validate(email.extraction)
    assert reviewed.review == [] and reviewed.inherited == ["po_number", "unit_price"]
    assert email.status == "analysed"


def test_a_po_number_that_arrived_alone_is_inherited_later(store):
    record_email_po(store, _email(store), _po(po_number="OR-5521", buyer="Orchard Row Ltd", style="OR-SW-40",
                    delivery_date="2027-03-05"), [], "")

    result = record_email_po(store, _email(store), _po(buyer="Orchard Row Ltd", style="OR-SW-40",
                             delivery_date="2027-03-05"), [], "")

    assert result.previous["po_number"] == "OR-5521"
