from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, get_router
from app.main import app
from app.models import Email, EmailAttachment, LLMCall

PO_TEXT = """ACME APPAREL LTD
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


@pytest.fixture
def emails(session_factory) -> dict[str, int]:
    with session_factory() as session:
        po = Email(
            sender="Buyer <buyer@acme.example>",
            subject="New order PO AB-1001",
            body="Please find our purchase order attached.",
            attachments=[
                EmailAttachment(filename="po.pdf", content_type="application/pdf", text_content=PO_TEXT)
            ],
        )
        query = Email(
            sender="Buyer <buyer@acme.example>",
            subject="Shipment status",
            body="Where is the shipment for our last order?",
        )
        session.add_all([po, query])
        session.commit()
        return {"po": po.id, "query": query.id}


def _call_count(session_factory) -> int:
    with session_factory() as session:
        return session.query(LLMCall).count()


def test_list_and_detail(client, emails):
    listing = client.get("/api/emails").json()
    assert {row["id"] for row in listing} == set(emails.values())
    assert all(row["status"] == "new" for row in listing)

    detail = client.get(f"/api/emails/{emails['po']}").json()
    assert detail["attachments"][0]["filename"] == "po.pdf"
    assert detail["extraction"] is None


def test_unknown_email_is_404(client):
    assert client.get("/api/emails/999").status_code == 404
    assert client.post("/api/emails/999/analyse").status_code == 404


def test_analyse_stores_classification_and_extraction_with_confidence(client, emails):
    body = client.post(f"/api/emails/{emails['po']}/analyse").json()

    assert body["status"] == "analysed"
    assert body["classification"]["category"] == "new_po"
    fields = body["extraction"]["fields"]
    assert fields["po_number"]["value"] == "AB-1001"
    assert fields["total_quantity"]["value"] == 1000
    assert fields["delivery_date"]["value"] == "2026-12-15"
    assert 0 < fields["po_number"]["confidence"] <= 1
    assert fields["line_items"][0]["sizes"] == {"S": 400, "M": 600}
    assert body["extraction"]["review"] == []

    assert client.get(f"/api/emails/{emails['po']}").json()["extraction"] == body["extraction"]


def test_email_without_po_data_skips_extraction(client, emails, session_factory):
    body = client.post(f"/api/emails/{emails['query']}/analyse").json()

    assert body["classification"]["has_po_data"] is False
    assert body["extraction"] is None
    assert body["status"] == "analysed"
    assert _call_count(session_factory) == 1


def test_second_analyse_returns_the_stored_result_without_new_calls(client, emails, session_factory):
    client.post(f"/api/emails/{emails['po']}/analyse")
    calls = _call_count(session_factory)

    body = client.post(f"/api/emails/{emails['po']}/analyse").json()

    assert body["notice"] == "Showing the stored analysis."
    assert _call_count(session_factory) == calls

    client.post(f"/api/emails/{emails['po']}/analyse", params={"force": True})
    assert _call_count(session_factory) > calls


def test_rate_limit_returns_429(client, emails, settings, monkeypatch):
    settings.rate_limit_per_minute = 2
    monkeypatch.setattr(rate_limit, "get_settings", lambda: settings)
    url = f"/api/emails/{emails['query']}/analyse"

    responses = [client.post(url) for _ in range(3)]

    assert [r.status_code for r in responses] == [200, 200, 429]
    assert "Rate limit" in responses[-1].json()["detail"]
    assert client.get("/api/emails").status_code == 200


def test_spend_cap_serves_stored_result_or_429(client, emails, settings, session_factory):
    client.post(f"/api/emails/{emails['po']}/analyse")

    settings.llm_mode = "live"
    settings.daily_spend_cap_usd = Decimal("0.01")
    with session_factory() as session:
        session.add(LLMCall(task_type="classify", tier="nano", model="m", cost_usd=Decimal("0.02")))
        session.commit()

    stored = client.post(f"/api/emails/{emails['po']}/analyse", params={"force": True})
    assert stored.status_code == 200
    assert "spend cap" in stored.json()["notice"]
    assert stored.json()["extraction"] is not None

    fresh = client.post(f"/api/emails/{emails['query']}/analyse")
    assert fresh.status_code == 429
    assert "spend cap" in fresh.json()["detail"]
