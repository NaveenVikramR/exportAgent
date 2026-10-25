"""Fixes from the live six-scenario test (docs/test-run/REPORT.md): T1, T2, T4, T5."""

from datetime import date

import pytest

from app.agent.tools.feasibility import check_feasibility
from app.schemas.extraction import EmailCategory, POExtraction
from app.services.normalise import normalise_extraction
from app.services.places import names_country
from app.services.profiles import load_profile
from app.services.review import review_extraction


def _po(**values) -> POExtraction:
    return POExtraction.model_validate(
        {k: {"value": v, "confidence": 0.9, "evidence": str(v)} for k, v in values.items() if k != "line_items"}
        | {"line_items": values.get("line_items", [])}
    )


T4 = """From: Tom Reyes <tom@bluekite-goods.example>
Subject: PO BK-7781 polo order

PO BK-7781, style BK-PL-02 piqué polo, colour Forest Green 1,500 pcs (S 300 / M 500 / L 500 / XL 200),
price USD 6.75, FOB Chennai, ex-factory 03/02/2027.

Thanks,
Tom
Blue Kite Goods"""


# --- destination must be stated (T4) -----------------------------------------------------------


def test_an_inferred_destination_is_dropped_and_the_date_stays_ambiguous():
    # Nano said "United States" from the buyer's name; nothing in the email says so.
    extraction = _po(po_number="BK-7781", destination_country="United States", delivery_date="2027-03-02")

    notes = normalise_extraction(extraction, T4)

    assert extraction.destination_country.value is None
    assert any("not stated" in note for note in notes)
    # With no destination, 03/02/2027 reads both ways: it is flagged instead of guessed.
    assert extraction.ambiguous_dates == ["delivery_date"]


@pytest.mark.parametrize(("text", "country", "named"), [
    ("Destination: United States (Savannah, GA)", "United States", True),
    ("so it lands in Melbourne for winter", "Australia", True),
    ("to our Vancouver warehouse", "Canada", True),
    ("Orchard Row Ltd, Bristol", "United Kingdom", True),
    ("Ship to USA", "United States", True),
    ("Please send us the samples", "United States", False),  # the pronoun, not the country
    ("Blue Kite Goods", "United States", False),
])
def test_names_country(text, country, named):
    assert names_country(text, country) is named


# --- style is not the PO number (T2) -----------------------------------------------------------


def test_the_po_number_copied_into_style_is_dropped():
    extraction = _po(po_number="HLA-24019 Rev A", style="HLA-24019")

    notes = normalise_extraction(extraction, "Revised PO HLA-24019 Rev A: Deep Navy 2,400, new total 3,600 pcs.")

    assert extraction.po_number.value == "HLA-24019" and extraction.po_revision == "A"
    assert extraction.style.value is None  # the follow-up keeps the order's style: no false change
    assert any("is the PO number" in note for note in notes)


def test_a_style_the_email_names_equal_to_the_po_is_kept():
    extraction = _po(po_number="KT-500", style="KT-500")

    normalise_extraction(extraction, "PO KT-500\nStyle No: KT-500 kids tee")

    assert extraction.style.value == "KT-500"


# --- two prices in one new PO (T5) -------------------------------------------------------------

T5 = """our order NW-5520 for the hoodie NW-HD-14, at EUR 11,40 as agreed on the phone.

Artikel: NW-HD-14 Kapuzenpullover
Preis: EUR 11,90 / Stück
Farbe          S     M     L     XL    Summe
Waldgrün       100   200   200   100   600
Gesamt: 1.400 Stück
Gesamtwert: EUR 16.660,00"""


def test_a_second_unit_price_in_a_new_po_is_flagged():
    extraction = _po(unit_price="11.90", total_quantity=1400)

    reviewed = review_extraction(extraction, T5, EmailCategory.NEW_PO, threshold=0.7)

    [flag] = [f for f in reviewed.review if f.reason == "price_conflict"]
    assert flag.field == "unit_price" and "11.40" in flag.detail


def test_totals_and_quantities_are_not_read_as_prices():
    extraction = _po(unit_price="7.20", total_quantity=2000)
    text = "Unit price: USD 7.20\nTotal: 2,000 pcs\nTotal value: USD 14,400.00\nGesamtwert: EUR 10.800,00"

    reviewed = review_extraction(extraction, text, EmailCategory.NEW_PO, threshold=0.7)

    assert not [f for f in reviewed.review if f.reason == "price_conflict"]


def test_a_revision_quoting_the_old_price_is_not_a_conflict():
    extraction = _po(unit_price="5.10")

    reviewed = review_extraction(extraction, "Price up from USD 4.85 to USD 5.10.", EmailCategory.PO_REVISION, 0.7)

    assert not [f for f in reviewed.review if f.reason == "price_conflict"]
