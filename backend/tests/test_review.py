from app.schemas.extraction import EmailCategory, POExtraction
from app.services.review import review_extraction

SOURCE = """PO Number: AB-1001
Style No: AB-TS-100
Buyer: Acme Apparel Ltd
Currency: USD, Unit Price: 4.00
Total Quantity: 1,000 pcs
Delivery Date: 15 December 2026
FOB Chennai, Destination: Germany"""


def _full(**overrides) -> POExtraction:
    data = {
        "buyer": {"value": "Acme Apparel Ltd", "confidence": 0.9, "evidence": "Buyer: Acme Apparel Ltd"},
        "po_number": {"value": "AB-1001", "confidence": 0.9, "evidence": "PO Number: AB-1001"},
        "style": {"value": "AB-TS-100", "confidence": 0.9, "evidence": "Style No: AB-TS-100"},
        "currency": {"value": "USD", "confidence": 0.9, "evidence": "Currency: USD"},
        "unit_price": {"value": "4.00", "confidence": 0.9, "evidence": "Unit Price: 4.00"},
        "total_quantity": {"value": 1000, "confidence": 0.9, "evidence": "Total Quantity: 1,000 pcs"},
        "delivery_date": {"value": "2026-12-15", "confidence": 0.9, "evidence": "15 December 2026"},
        "incoterms": {"value": "FOB", "confidence": 0.9, "evidence": "FOB Chennai"},
        "port": {"value": "Chennai", "confidence": 0.9, "evidence": "FOB Chennai"},
        "destination_country": {"value": "Germany", "confidence": 0.9, "evidence": "Destination: Germany"},
        "line_items": [
            {"colour": "Navy", "sizes": {"S": 400, "M": 600}, "quantity": 1000},
        ],
    }
    data.update(overrides)
    return POExtraction.model_validate(data)


def _review(extraction, category=EmailCategory.NEW_PO):
    return review_extraction(extraction, SOURCE, category, threshold=0.7)


def _flags(reviewed) -> set[tuple[str, str]]:
    return {(flag.field, flag.reason) for flag in reviewed.review}


def test_clean_extraction_has_no_flags():
    assert _review(_full()).review == []


def test_evidence_is_matched_ignoring_case_and_whitespace():
    extraction = _full(po_number={"value": "AB-1001", "confidence": 0.9, "evidence": "po  number:\nAB-1001"})

    assert _review(extraction).review == []


def test_evidence_not_in_email_lowers_confidence_and_flags():
    extraction = _full(unit_price={"value": "4.50", "confidence": 0.95, "evidence": "Unit Price: 4.50"})

    reviewed = _review(extraction)

    assert ("unit_price", "evidence_not_found") in _flags(reviewed)
    assert reviewed.fields.unit_price.confidence == 0.4


def test_missing_required_field_is_flagged_for_a_new_po():
    extraction = _full(delivery_date={"value": None, "confidence": 0.8, "evidence": None})

    reviewed = _review(extraction)

    assert ("delivery_date", "missing") in _flags(reviewed)
    assert reviewed.fields.delivery_date.confidence == 0


def test_change_notice_only_requires_the_po_number():
    extraction = POExtraction.model_validate(
        {
            "po_number": {"value": "AB-1001", "confidence": 0.9, "evidence": "PO Number: AB-1001"},
            "delivery_date": {"value": "2026-12-15", "confidence": 0.9, "evidence": "15 December 2026"},
        }
    )

    assert _review(extraction, EmailCategory.DELIVERY_CHANGE).review == []
    assert ("po_number", "missing") in _flags(_review(POExtraction(), EmailCategory.DELIVERY_CHANGE))


def test_code_value_missing_from_its_quote_is_flagged():
    # The quote is real text from the email, but it does not state a currency.
    extraction = _full(currency={"value": "USD", "confidence": 1.0, "evidence": "Buyer: Acme Apparel Ltd"})

    reviewed = _review(extraction)

    assert _flags(reviewed) == {("currency", "evidence_mismatch")}
    assert reviewed.fields.currency.confidence == 0.4


def test_currency_symbol_counts_as_stating_the_currency():
    source = SOURCE + "\nPrice per unit: £2.95"
    extraction = _full(currency={"value": "GBP", "confidence": 0.9, "evidence": "£2.95"})

    reviewed = review_extraction(extraction, source, EmailCategory.NEW_PO, threshold=0.7)

    assert ("currency", "evidence_mismatch") not in _flags(reviewed)


def test_size_breakdown_counts_towards_total_when_line_quantity_is_missing():
    extraction = _full(line_items=[{"colour": "Navy", "sizes": {"S": 750, "M": 750}, "quantity": None}])

    assert ("total_quantity", "quantity_mismatch") in _flags(_review(extraction))


def test_low_model_confidence_is_flagged():
    extraction = _full(port={"value": "Chennai", "confidence": 0.5, "evidence": "FOB Chennai"})

    assert _flags(_review(extraction)) == {("port", "low_confidence")}


def test_line_items_not_adding_up_to_total_is_flagged():
    extraction = _full(
        line_items=[
            {"colour": "Navy", "sizes": {"S": 400, "M": 600}, "quantity": 1000},
            {"colour": "White", "sizes": {}, "quantity": 400},
        ]
    )

    reviewed = _review(extraction)

    assert ("total_quantity", "quantity_mismatch") in _flags(reviewed)
    assert reviewed.fields.total_quantity.confidence == 0.4


def test_sizes_not_adding_up_to_line_total_is_flagged():
    extraction = _full(line_items=[{"colour": "Navy", "sizes": {"S": 400, "M": 500}, "quantity": 1000}])

    assert ("line_items", "quantity_mismatch") in _flags(_review(extraction))


def test_review_does_not_mutate_the_input():
    extraction = _full(unit_price={"value": "4.50", "confidence": 0.95, "evidence": "nope"})

    _review(extraction)

    assert extraction.unit_price.confidence == 0.95
