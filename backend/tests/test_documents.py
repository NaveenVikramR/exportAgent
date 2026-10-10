from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent.loop import run_agent
from app.api import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, get_router
from app.main import app
from app.models import Email, Order
from app.services.documents import generate as generate_module
from app.services.documents.compute import (
    TBC,
    amount_in_words,
    build_invoice,
    build_packing_list,
    number_in_words,
    round_money,
)
from app.services.documents.render import FOOTER, render_invoice, render_packing_list
from app.services.profiles import load_profile
from tests.test_agent import demo, fake_search  # noqa: F401  (pytest fixture and helper)

INDIA = load_profile("india_tiruppur")
BANGLADESH = load_profile("bangladesh_dhaka")
ON = date(2026, 10, 10)
ORDER = SimpleNamespace(id=7, po_number="NW-45120", buyer="Nordwind Mode GmbH")


def _po(**overrides) -> dict:
    data = {
        "buyer": "Nordwind Mode GmbH", "po_number": "NW-45120", "style": "NW-TS-2207", "currency": "USD",
        "unit_price": "4.85", "total_quantity": 13500, "delivery_date": "2026-11-30", "incoterms": "FOB",
        "port": "Tuticorin", "destination_country": "Germany",
        "line_items": [
            {"colour": "Navy", "sizes": {"S": 800, "M": 2000, "L": 2000, "XL": 1200}, "quantity": 6000, "unit_price": None},
            {"colour": "White", "sizes": {"S": 600, "M": 1500, "L": 1500, "XL": 900}, "quantity": 4500, "unit_price": None},
            {"colour": "Heather Grey", "sizes": {"S": 400, "M": 1000, "L": 1000, "XL": 600}, "quantity": 3000, "unit_price": None},
        ],
    }
    return data | overrides


def _invoice(profile=INDIA, **overrides):
    return build_invoice(ORDER, _po(**overrides), 2, profile, ON)


def _packing(profile=INDIA, **overrides):
    return build_packing_list(ORDER, _po(**overrides), 2, profile, ON, "INV-1")


# --- money --------------------------------------------------------------------------------


@pytest.mark.parametrize(("amount", "currency", "expected"), [
    ("2.345", "USD", "2.35"),      # half-up, not banker's rounding (which gives 2.34)
    ("2.355", "USD", "2.36"),
    ("2.344999", "USD", "2.34"),
    ("1000.5", "JPY", "1001"),     # no minor unit
    ("19040", "GBP", "19040.00"),
])
def test_currency_rounding(amount, currency, expected):
    assert str(round_money(Decimal(amount), currency)) == expected


def test_invoice_lines_and_total():
    invoice = _invoice()

    assert [(line.colour, line.quantity, line.amount) for line in invoice.lines] == [
        ("Navy", 6000, Decimal("29100.00")), ("White", 4500, Decimal("21825.00")),
        ("Heather Grey", 3000, Decimal("14550.00")),
    ]
    assert (invoice.total_quantity, invoice.total_amount) == (13500, Decimal("65475.00"))
    assert invoice.amount_in_words == "US Dollars Sixty-Five Thousand Four Hundred Seventy-Five Only"
    assert invoice.lines[0].hs_code == "6109.10"


def test_total_is_the_sum_of_rounded_line_amounts():
    # 1001 x 2.955 = 2957.955 -> 2957.96 and 1 x 0.005 -> 0.01: total 2957.97,
    # whereas rounding the unrounded sum (2957.960) would give 2957.96.
    invoice = _invoice(line_items=[
        {"colour": "A", "sizes": {}, "quantity": 1001, "unit_price": "2.955"},
        {"colour": "B", "sizes": {}, "quantity": 1, "unit_price": "0.005"},
    ])

    assert [line.amount for line in invoice.lines] == [Decimal("2957.96"), Decimal("0.01")]
    assert invoice.total_amount == Decimal("2957.97")


def test_line_price_overrides_the_order_price():
    invoice = _invoice(line_items=[
        {"colour": "Navy", "sizes": {}, "quantity": 100, "unit_price": "5.10"},
        {"colour": "White", "sizes": {}, "quantity": 100, "unit_price": None},
    ])

    assert [line.unit_price for line in invoice.lines] == [Decimal("5.10"), Decimal("4.85")]
    assert invoice.total_amount == Decimal("995.00")


def test_yen_invoice_has_no_decimals():
    invoice = _invoice(currency="JPY", unit_price="333.5", line_items=[{"colour": "Navy", "sizes": {}, "quantity": 3}])

    assert invoice.total_amount == Decimal("1001")
    assert invoice.amount_in_words == "Japanese Yen One Thousand One Only"


@pytest.mark.parametrize(("amount", "currency", "words"), [
    ("1234.56", "USD", "US Dollars One Thousand Two Hundred Thirty-Four and Cents Fifty-Six Only"),
    ("19040.00", "GBP", "Pounds Sterling Nineteen Thousand Forty Only"),
    ("0.50", "EUR", "Euros Zero and Cents Fifty Only"),
    ("2000000.01", "AUD", "Australian Dollars Two Million and Cents One Only"),
])
def test_amount_in_words(amount, currency, words):
    assert amount_in_words(Decimal(amount), currency) == words


def test_number_in_words_edges():
    assert number_in_words(115) == "One Hundred Fifteen"
    assert number_in_words(1_000_017) == "One Million Seventeen"


# --- missing data is never guessed --------------------------------------------------------------


def test_missing_price_is_to_be_confirmed_not_guessed():
    invoice = _invoice(unit_price=None)

    assert all(line.amount is None for line in invoice.lines)
    assert invoice.total_amount is None and invoice.amount_in_words == TBC
    assert "Unit price" in invoice.tbc_fields


def test_style_not_in_catalogue_leaves_description_hs_code_and_weights_to_confirm():
    invoice = _invoice(style="MC-PL-118")
    packing = _packing(style="MC-PL-118")

    assert invoice.lines[0].hs_code == TBC and invoice.lines[0].description == TBC
    assert {"HS code", "Goods description"} <= set(invoice.tbc_fields)
    assert packing.total_net_kg is None and packing.rows[0].gross_kg is None
    assert {"Net weight per piece", "Carton dimensions"} <= set(packing.tbc_fields)
    assert packing.rows[0].pcs_per_carton == INDIA.documents.packing.default_pcs_per_carton
    assert any("factory default" in note for note in packing.notes)


def test_registration_and_bank_details_are_to_be_confirmed_until_configured():
    invoice = _invoice()

    assert dict(invoice.registration) == {name: TBC for name in INDIA.documents.format.registration_fields}
    assert all(value == TBC for _, value in invoice.bank)
    assert invoice.consignee == TBC and invoice.payment_terms == TBC


# --- ports and Incoterms ---------------------------------------------------------------------


def test_fob_named_place_is_the_port_of_loading():
    invoice = _invoice()

    assert (invoice.port_of_loading, invoice.port_of_discharge) == ("Tuticorin", TBC)


def test_cif_named_place_is_the_port_of_discharge():
    invoice = _invoice(incoterms="CIF", port="Felixstowe")

    assert (invoice.port_of_loading, invoice.port_of_discharge) == ("Tuticorin", "Felixstowe")
    assert build_invoice(ORDER, _po(incoterms="CIF", port="Felixstowe"), 2, BANGLADESH, ON).port_of_loading == "Chittagong"


def test_missing_incoterm_is_to_be_confirmed():
    assert _invoice(incoterms=None).incoterm == TBC


# --- country formats ---------------------------------------------------------------------------


def test_country_profile_drives_format_numbering_and_currency_default():
    india, bangladesh = _invoice(currency=None), build_invoice(ORDER, _po(currency=None), 2, BANGLADESH, ON)

    assert india.number == "SVK/EXP/2026/0007-2" and bangladesh.number == "MKC/EXP/2026/0007-2"
    assert india.country_of_origin == "India" and bangladesh.country_of_origin == "Bangladesh"
    assert "IEC Code" in dict(india.registration) and "ERC No." in dict(bangladesh.registration)
    assert any("IGST" in text for text in india.declarations)
    assert any("Bangladesh origin" in text for text in bangladesh.declarations)
    assert india.currency == INDIA.export_currency == "USD"


# --- packing list ------------------------------------------------------------------------------


def test_cartons_by_colour_and_size_with_remainders():
    packing = _packing(style="HF-KL-0932", line_items=[
        {"colour": "Sage", "sizes": {"2-3Y": 400, "4-5Y": 600}, "quantity": 1000},
        {"colour": "Charcoal", "sizes": {"2-3Y": 30}, "quantity": 30},
    ])

    assert [(r.carton_from, r.carton_to, r.colour, r.size, r.pcs_per_carton, r.cartons, r.quantity) for r in packing.rows] == [
        (1, 6, "Sage", "2-3Y", 60, 6, 360),
        (7, 7, "Sage", "2-3Y", 40, 1, 40),
        (8, 17, "Sage", "4-5Y", 60, 10, 600),
        (18, 18, "Charcoal", "2-3Y", 30, 1, 30),
    ]
    assert (packing.total_cartons, packing.total_quantity) == (18, 1030)


def test_weights_and_volume():
    packing = _packing()  # 50 pcs per carton, 0.17 kg per piece, 0.9 kg per carton, 60 x 40 x 30 cm

    assert (packing.total_cartons, packing.total_quantity) == (270, 13500)
    assert packing.total_net_kg == Decimal("2295.00")
    assert packing.total_gross_kg == Decimal("2538.00")  # 2295 + 270 x 0.9
    assert packing.total_cbm == Decimal("19.440")
    first = packing.rows[0]
    assert (first.cartons, first.net_kg, first.gross_kg) == (16, Decimal("136.00"), Decimal("150.40"))
    assert sum(r.net_kg for r in packing.rows) == packing.total_net_kg


def test_weight_rounding_is_half_up_per_row():
    packing = _packing(style="HF-KL-0932", line_items=[{"colour": "Sage", "sizes": {"S": 5}, "quantity": 5}])

    # 5 x 0.11 = 0.55 net; + 1 carton x 0.9 tare = 1.45 gross
    assert (packing.rows[0].net_kg, packing.rows[0].gross_kg) == (Decimal("0.55"), Decimal("1.45"))


def test_no_size_breakdown_packs_as_assorted():
    packing = _packing(line_items=[{"colour": "Blanc", "sizes": {}, "quantity": 2025}])

    assert [(r.size, r.cartons, r.quantity) for r in packing.rows] == [("Assorted", 40, 2000), ("Assorted", 1, 25)]
    assert any("no size breakdown" in note for note in packing.notes)


def test_no_line_items_uses_the_total_quantity():
    invoice, packing = _invoice(line_items=[]), _packing(line_items=[])

    assert [(line.colour, line.quantity) for line in invoice.lines] == [("As per PO", 13500)]
    assert packing.total_quantity == 13500


def test_pdfs_render():
    invoice_pdf = render_invoice(_invoice())
    packing_pdf = render_packing_list(_packing(style="MC-PL-118"))

    assert invoice_pdf.startswith(b"%PDF") and packing_pdf.startswith(b"%PDF")
    assert len(invoice_pdf) > 2000
    assert "ExportAgent" in FOOTER and "verify before use" in FOOTER


# --- API: approve the reply, then generate --------------------------------------------------------


@pytest.fixture
def client(session_factory, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(generate_module, "GENERATED_DIR", tmp_path)
    settings.llm_mode = "mock"

    def override():
        with session_factory() as session:
            yield session

    rate_limit.reset()
    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_router] = lambda: LLMRouter(settings, session_factory=session_factory)
    yield TestClient(app)
    app.dependency_overrides.clear()
    rate_limit.reset()


def _assess_and_draft(client, session_factory, settings, email_id) -> tuple[int, int]:
    with session_factory() as session:
        email = session.get(Email, email_id)
        run_agent(session, email, LLMRouter(settings, session_factory=session_factory), search=fake_search)
        order_id = email.order_id
    reply = next(d for d in client.post(f"/api/emails/{email_id}/drafts").json() if d["kind"] == "buyer_reply")
    return order_id, reply["id"]


def test_reply_with_alternatives_waits_for_the_buyer_then_split_documents(client, session_factory, settings, demo):
    order_id, reply_id = _assess_and_draft(client, session_factory, settings, demo)
    assert client.post(f"/api/orders/{order_id}/documents").status_code == 409

    approved = client.post(f"/api/drafts/{reply_id}/approve", json={"reviewer": "Karthik"}).json()
    assert approved["offer"]["action"] == "record_buyer_decision"
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "awaiting_buyer"
    blocked = client.post(f"/api/orders/{order_id}/documents")
    assert blocked.status_code == 409 and "buyer's decision" in blocked.json()["detail"]

    options = {o["id"]: o for o in client.get(f"/api/orders/{order_id}/decision-options").json()}
    assert set(options) == {"as_requested", "full_by_earliest", "split"}
    assert [s["quantity"] for s in options["split"]["shipments"]] == [9300, 4200]
    assert client.post(f"/api/orders/{order_id}/decision", json={"choice": "nope", "decided_by": "K"}).status_code == 400

    decided = client.post(f"/api/orders/{order_id}/decision", json={"choice": "split", "decided_by": "Karthik"}).json()
    assert decided["status"] == "confirmed" and decided["version"] == 3
    order = client.get(f"/api/orders/{order_id}").json()
    latest = order["versions"][0]
    assert latest["basis"] == "buyer_decision" and latest["email_id"] is None
    assert latest["data"]["delivery_date"] == options["split"]["shipments"][1]["delivery_date"]
    assert any(c["field"] == "buyer_decision" and "Karthik" in c["detail"] for c in latest["changes"])

    documents = client.post(f"/api/orders/{order_id}/documents").json()
    invoices = [d for d in documents if d["kind"] == "commercial_invoice"]
    packing = [d for d in documents if d["kind"] == "packing_list"]
    assert len(invoices) == len(packing) == 2
    assert [d["number"].rsplit("-", 1)[-1] for d in invoices] == ["S1", "S2"]
    assert [d["totals"]["total_quantity"] for d in invoices] == [9300, 4200]
    assert sum(Decimal(d["totals"]["total_amount"]) for d in invoices) == Decimal("65475.00")
    assert invoices[0]["shipment"].startswith("Shipment 1 of 2: 9,300 pcs")

    pdf = client.get(invoices[1]["download_url"])
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_accepted_as_requested_gives_one_shipment(client, session_factory, settings, demo):
    order_id, reply_id = _assess_and_draft(client, session_factory, settings, demo)
    client.post(f"/api/drafts/{reply_id}/approve", json={"reviewer": "Karthik"})

    client.post(f"/api/orders/{order_id}/decision", json={"choice": "as_requested", "decided_by": "Karthik"})
    documents = client.post(f"/api/orders/{order_id}/documents").json()

    assert [d["kind"] for d in documents] == ["commercial_invoice", "packing_list"]
    assert documents[0]["shipment"] is None and documents[0]["totals"]["total_quantity"] == 13500


def test_reply_without_alternatives_confirms_the_order(client, session_factory, settings):
    with session_factory() as session:
        from tests.test_agent import _email

        email = _email(session, "AB-2001", 1000, "2027-02-15", "2026-09-01")
        email_id = email.id
    order_id, reply_id = _assess_and_draft(client, session_factory, settings, email_id)

    approved = client.post(f"/api/drafts/{reply_id}/approve", json={"reviewer": "Karthik"}).json()

    assert approved["offer"]["action"] == "generate_documents"
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "confirmed"
    assert client.post(f"/api/orders/{order_id}/documents").status_code == 200


def test_new_po_version_reopens_the_order_and_drops_the_agreed_plan(client, session_factory, settings, demo):
    order_id, reply_id = _assess_and_draft(client, session_factory, settings, demo)
    client.post(f"/api/drafts/{reply_id}/approve", json={"reviewer": "Karthik"})
    client.post(f"/api/orders/{order_id}/decision", json={"choice": "split", "decided_by": "Karthik"})

    with session_factory() as session:
        from tests.test_agent import _email

        _email(session, "NW-45120", 14000, "2026-12-20", "2026-09-25", subject="Revision 2")
    order = client.get(f"/api/orders/{order_id}").json()

    assert order["status"] == "open"
    assert "shipments" not in order["versions"][0]["data"]
    assert client.post(f"/api/orders/{order_id}/documents").status_code == 409




def test_split_shipments_allocate_every_colour_and_size():
    from app.services.documents.compute import split_shipments

    data = _po(shipments=[{"quantity": 9300, "delivery_date": "2026-11-30"},
                          {"quantity": 4200, "delivery_date": "2026-12-08"}])

    first, second = split_shipments(data)

    assert (first["total_quantity"], second["total_quantity"]) == (9300, 4200)
    assert (first["delivery_date"], second["delivery_date"]) == ("2026-11-30", "2026-12-08")
    for original, a, b in zip(data["line_items"], first["line_items"], second["line_items"]):
        assert a["colour"] == b["colour"] == original["colour"]
        for size, qty in original["sizes"].items():
            assert a["sizes"][size] + b["sizes"][size] == qty
        assert a["quantity"] == sum(a["sizes"].values())
    # roughly the same share of every cell: Navy M is 2,000 of 13,500
    assert first["line_items"][0]["sizes"]["M"] in (1377, 1378)


def test_split_shipment_invoices_add_up_to_the_order():
    from app.services.documents.compute import split_shipments

    data = _po(shipments=[{"quantity": 9300, "delivery_date": "2026-11-30"},
                          {"quantity": 4200, "delivery_date": "2026-12-08"}])

    invoices = [build_invoice(ORDER, part, 3, INDIA, ON) for part in split_shipments(data)]

    assert [i.number for i in invoices] == ["SVK/EXP/2026/0007-3-S1", "SVK/EXP/2026/0007-3-S2"]
    assert sum(i.total_amount for i in invoices) == Decimal("65475.00")
    assert invoices[0].shipment == "Shipment 1 of 2: 9,300 pcs, ex-factory 2026-11-30"


def test_single_shipment_plan_is_one_document_set():
    from app.services.documents.compute import split_shipments

    data = _po(shipments=[{"quantity": 13500, "delivery_date": "2026-12-08"}])

    assert split_shipments(data) == [data]
