import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, get_router
from app.main import app
from app.models import Email, EmailAttachment, Order, POVersion
from app.schemas.extraction import POExtraction
from app.schemas.orders import DELIVERY_PULLED_FORWARD, StatedChange
from app.services.orders import find_order, record_po_version


def _extraction(**values) -> POExtraction:
    fields = {"po_number": "AB-1001", "buyer": "Acme Ltd", "unit_price": "4.00",
              "total_quantity": 1000, "delivery_date": "2026-12-15"} | values
    data = {
        name: {"value": value, "confidence": 0.9, "evidence": str(value)}
        for name, value in fields.items() if name != "line_items"
    }
    data["line_items"] = fields.get("line_items", [])
    return POExtraction.model_validate(data)


@pytest.fixture
def session(session_factory):
    with session_factory() as session:
        yield session


def _email(session, subject="PO") -> Email:
    email = Email(sender="buyer@acme.example", subject=subject, body="...")
    session.add(email)
    session.flush()
    return email


def test_first_email_creates_order_version_1(session):
    email = _email(session)

    version = record_po_version(session, email, _extraction(), [])
    session.commit()

    order = session.scalar(select(Order))
    assert (order.po_number, order.buyer, order.current_version) == ("AB-1001", "Acme Ltd", 1)
    assert (version.version, version.basis, version.changes) == (1, "document", [])
    assert version.data["unit_price"] == "4.00"
    assert version.confidence["po_number"] == 0.9
    assert email.order_id == order.id


def test_revision_appends_a_version_and_keeps_the_old_one(session):
    record_po_version(session, _email(session), _extraction(), [])
    record_po_version(session, _email(session), _extraction(unit_price="3.80", delivery_date="2026-12-01"), [])
    session.commit()

    versions = session.scalars(select(POVersion).order_by(POVersion.version)).all()
    assert [v.version for v in versions] == [1, 2]
    assert versions[0].data["unit_price"] == "4.00"
    assert versions[1].data["unit_price"] == "3.80"
    assert {c["field"] for c in versions[1].changes} == {"unit_price", "delivery_date"}
    alerts = [c["alert"] for c in versions[1].changes if c["alert"]]
    assert alerts == [DELIVERY_PULLED_FORWARD]
    assert session.scalar(select(Order)).current_version == 2


def test_po_number_matching_ignores_case_and_spaces(session):
    record_po_version(session, _email(session), _extraction(po_number="HF/PO/26/3391"), [])
    session.commit()

    assert find_order(session, "hf/po/26/ 3391") is not None
    record_po_version(session, _email(session), _extraction(po_number="hf/po/26/3391", unit_price="3.90"), [])
    session.commit()
    assert session.query(Order).count() == 1


def test_partial_update_carries_unstated_values_forward(session):
    record_po_version(session, _email(session), _extraction(), [])
    partial = POExtraction.model_validate(
        {"po_number": {"value": "AB-1001", "confidence": 0.9},
         "delivery_date": {"value": "2026-12-01", "confidence": 0.9}}
    )

    version = record_po_version(session, _email(session), partial, [])

    assert version.data["unit_price"] == "4.00"
    assert [c["field"] for c in version.changes] == ["delivery_date"]


def test_resend_without_changes_adds_no_version(session):
    record_po_version(session, _email(session), _extraction(), [])
    email = _email(session)

    assert record_po_version(session, email, _extraction(), []) is None
    session.commit()
    assert session.query(POVersion).count() == 1
    assert email.order_id is not None


def test_same_email_never_adds_a_second_version(session):
    email = _email(session)
    record_po_version(session, email, _extraction(), [])
    record_po_version(session, _email(session), _extraction(unit_price="3.80"), [])

    again = record_po_version(session, email, _extraction(unit_price="9.99"), [])

    assert again.version == 1
    assert session.query(POVersion).count() == 2


def test_thread_quote_rebuilds_the_earlier_version(session):
    stated = [StatedChange(field="delivery_date", old="2026-11-24", new="2026-11-10")]

    version = record_po_version(session, _email(session), _extraction(delivery_date="2026-11-10"), stated)
    session.commit()

    versions = session.scalars(select(POVersion).order_by(POVersion.version)).all()
    assert [(v.version, v.basis, v.email_id is None) for v in versions] == [
        (1, "thread_reference", True), (2, "document", False)
    ]
    assert versions[0].data["delivery_date"] == "2026-11-24"
    assert version.changes[0]["alert"] == DELIVERY_PULLED_FORWARD


def test_no_po_number_creates_no_order(session):
    assert record_po_version(session, _email(session), _extraction(po_number=None), []) is None
    assert session.query(Order).count() == 0


# --- End to end through the API, in mock mode ---------------------------------------------

PO_V1 = """ACME APPAREL LTD
PURCHASE ORDER
PO Number: AB-1001
Style No: AB-TS-100
Currency: USD
Unit Price: 4.00 per piece
Incoterms: FOB Chennai
Destination: Hamburg, Germany
Delivery Date (ex-factory): 15 December 2026

Colour  S    M    Total
Navy    400  600  1000

Total Quantity: 1,000 pcs"""

PO_V2 = PO_V1.replace("15 December 2026", "01 December 2026").replace("PURCHASE ORDER", "PURCHASE ORDER - REVISION 1")


@pytest.fixture
def client(session_factory, settings):
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


def _seed_email(session_factory, subject, attachment) -> int:
    with session_factory() as session:
        email = Email(
            sender="Buyer <buyer@acme.example>", subject=subject, body="Please see the attached PO.",
            attachments=[EmailAttachment(filename="po.pdf", content_type="application/pdf", text_content=attachment)],
        )
        session.add(email)
        session.commit()
        return email.id


def test_revised_po_email_shows_up_as_version_2_with_alert(client, session_factory):
    first = _seed_email(session_factory, "New order PO AB-1001", PO_V1)
    second = _seed_email(session_factory, "Revised PO AB-1001", PO_V2)

    assert client.post(f"/api/emails/{first}/analyse").json()["order_id"] is not None
    order_id = client.post(f"/api/emails/{second}/analyse").json()["order_id"]

    [summary] = client.get("/api/orders").json()
    assert summary["id"] == order_id
    assert summary["current_version"] == 2
    assert summary["alerts"] == [DELIVERY_PULLED_FORWARD]

    detail = client.get(f"/api/orders/{order_id}").json()
    assert [v["version"] for v in detail["versions"]] == [2, 1]
    [change] = detail["versions"][0]["changes"]
    assert (change["field"], change["old"], change["new"]) == ("delivery_date", "2026-12-15", "2026-12-01")
    assert detail["versions"][0]["email_id"] == second

    # Re-running the analysis does not add or overwrite versions.
    client.post(f"/api/emails/{second}/analyse", params={"force": True})
    assert client.get(f"/api/orders/{order_id}").json()["current_version"] == 2


def test_unknown_order_is_404(client):
    assert client.get("/api/orders/999").status_code == 404
