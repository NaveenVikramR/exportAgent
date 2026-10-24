"""Milestone 8 endpoints: pasted and uploaded emails, dashboard, profiles, demo snapshot,
and the risk agent running in the background."""

import functools
import io
import time

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.api import agent as agent_api
from app.api.rate_limit import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, get_router
from app.main import app
from app.models import AgentRun, Email, Order
from app.services.demo import export_snapshot, load_snapshot
from app.agent.loop import run_agent
from tests.test_agent import demo, fake_search  # noqa: F401  (fixture)


@pytest.fixture
def client(session_factory, settings):
    settings.llm_mode = "mock"
    router = LLMRouter(settings, session_factory=session_factory)

    def session_override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_router] = lambda: router
    app.dependency_overrides[rate_limit] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    for i, line in enumerate(text.splitlines()):
        page.drawString(50, 800 - 14 * i, line)
    page.save()
    return buffer.getvalue()


def test_a_pasted_email_is_stored_unanalysed(client):
    email = client.post("/api/emails", json={"sender": "Ana <ana@x.example>", "subject": "New PO",
                                             "body": "Please book PO 4471: 2,000 tees, USD 4.10."}).json()

    assert email["status"] == "new" and email["classification"] is None
    assert client.get(f"/api/emails/{email['id']}").json()["subject"] == "New PO"


def test_a_pasted_email_needs_a_body(client):
    assert client.post("/api/emails", json={"body": "hi"}).status_code == 422


def test_an_uploaded_pdf_becomes_an_attachment(client):
    pdf = _pdf("PURCHASE ORDER PO-4471\nStyle TS-12 crew tee\nNavy 1,000 pcs\nUSD 4.10 FOB Chennai")

    email = client.post("/api/emails/upload", files={"file": ("PO-4471.pdf", pdf, "application/pdf")},
                        data={"sender": "Ana <ana@x.example>"}).json()

    [attachment] = email["attachments"]
    assert attachment["filename"] == "PO-4471.pdf" and "PO-4471" in attachment["text_content"]
    assert email["subject"] == "PO-4471"


@pytest.mark.parametrize(("content", "message"), [
    (b"not a pdf", "Please upload a PDF"),
    (_pdf(""), "no text layer"),
])
def test_unusable_uploads_are_explained(client, content, message):
    response = client.post("/api/emails/upload", files={"file": ("x.pdf", content, "application/pdf")})
    assert response.status_code == 422 and message in response.json()["detail"]


def test_dashboard_counts_what_needs_attention(client, session_factory, demo):  # noqa: F811
    data = client.get("/api/dashboard").json()

    assert data["open_orders"] == 2 and data["drafts_pending"] == 0
    assert data["spend"]["cap_usd"] == "1.00" and len(data["recent_emails"]) == 3


def test_profiles_compare_the_same_order(client, session_factory, demo):  # noqa: F811
    with session_factory() as session:
        order_id = session.get(Email, demo).order_id

    rows = {row["profile"]["id"]: row for row in client.get(f"/api/orders/{order_id}/profiles").json()}

    assert rows["india_tiruppur"]["feasibility"]["verdict"] == "infeasible"
    assert rows["india_tiruppur"]["feasibility"]["shortfall"] == 4186
    assert rows["bangladesh_dhaka"]["feasibility"]["verdict"] in ("feasible", "tight")
    assert rows["bangladesh_dhaka"]["invoice"]["country_of_origin"] != rows["india_tiruppur"]["invoice"]["country_of_origin"]

    assert client.patch(f"/api/orders/{order_id}/profile", json={"profile": "bangladesh_dhaka"}).json() == {"profile": "bangladesh_dhaka"}
    with session_factory() as session:
        assert session.get(Order, order_id).profile == "bangladesh_dhaka"
    assert client.patch(f"/api/orders/{order_id}/profile", json={"profile": "mars"}).status_code == 422


def test_profiles_check_an_agreed_split_shipment_by_shipment(client, session_factory, demo):  # noqa: F811
    from app.agent.tools.agent_tools import ToolContext, run_tool
    from app.api.profiles import _as_of
    from app.models import AgentStep
    from app.services.decisions import record_decision
    from app.services.profiles import load_profile

    with session_factory() as session:
        email = session.get(Email, demo)
        order = session.get(Order, email.order_id)
        # The options a risk run proposes, computed by the same Python tool.
        ctx = ToolContext(session=session, as_of=_as_of(session, order), profile=load_profile(order.profile))
        _args, options, _summary = run_tool(ctx, "propose_delivery_options", f'{{"order_id": {order.id}}}')
        run = AgentRun(email_id=email.id, order_id=order.id, status="completed", rounds=0,
                       result={"summary": "s", "flags": [], "info_checked": []})
        session.add(run)
        session.flush()
        session.add(AgentStep(run_id=run.id, seq=1, round=0, kind="tool", name="propose_delivery_options",
                              input={}, output=options))
        session.flush()
        record_decision(session, order, "split", "test")
        session.commit()
        order_id = order.id

    rows = {row["profile"]["id"]: row for row in client.get(f"/api/orders/{order_id}/profiles").json()}

    # 9,300 pcs by 30 Nov and the rest by the earliest full date: the plan the reply offered.
    tiruppur = rows["india_tiruppur"]["feasibility"]
    assert tiruppur["verdict"] in ("feasible", "tight")
    assert tiruppur["reason"].startswith("Agreed split: shipment 1 (9,300 pcs by 2026-11-30)")
    assert tiruppur["shortfall"] == 0
    assert rows["bangladesh_dhaka"]["feasibility"]["verdict"] in ("feasible", "tight")


def test_demo_snapshot_round_trip(session_factory, demo):  # noqa: F811
    with session_factory() as session:
        snapshot = export_snapshot(session)
        session.add(Email(sender="x", subject="pasted later", body="-", received_at=session.get(Email, demo).received_at))
        session.commit()

        counts = load_snapshot(session, snapshot)

        assert counts["emails"] == 3 and session.query(Email).count() == 3
        assert session.query(Order).count() == 2


def test_demo_reset_keeps_todays_spend(session_factory, settings, demo):  # noqa: F811
    from decimal import Decimal

    from app.models import LLMCall

    llm = LLMRouter(settings, session_factory=session_factory)
    with session_factory() as session:
        snapshot = export_snapshot(session)
        session.add(LLMCall(task_type="classify", tier="nano", model="m", input_tokens=1, output_tokens=1,
                            latency_ms=1, cost_usd=Decimal("0.25"), source="live", success=True))
        session.commit()
    before = llm.spent_today()

    with session_factory() as session:
        load_snapshot(session, snapshot)

    assert before >= Decimal("0.25")
    assert llm.spent_today() == before


def test_a_failed_rerun_keeps_showing_the_previous_assessment(client, session_factory, demo):  # noqa: F811
    with session_factory() as session:
        email = session.get(Email, demo)
        good = AgentRun(email_id=email.id, order_id=email.order_id, status="completed", rounds=1,
                        result={"summary": "stored", "flags": [], "checked": []})
        session.add(good)
        session.flush()
        session.add(AgentRun(email_id=email.id, order_id=email.order_id, status="failed", rounds=0,
                             error="No key."))
        session.commit()
        good_id = good.id

    body = client.get(f"/api/emails/{demo}/agent").json()

    assert body["id"] == good_id and body["status"] == "completed"
    assert "did not complete: No key." in body["notice"]


def test_the_routing_decision_reaches_the_page(client, session_factory, demo):  # noqa: F811
    from app.models import AgentStep

    with session_factory() as session:
        email = session.get(Email, demo)
        stored = AgentRun(email_id=email.id, order_id=email.order_id, status="completed", rounds=1,
                          result={"summary": "new", "flags": [], "info_checked": [],
                                  "routing": {"tier": "super", "escalated": False, "reasons": [], "super_attempted": True}})
        older = AgentRun(email_id=email.id, order_id=email.order_id, status="completed", rounds=1,
                         result={"summary": "old", "flags": [], "info_checked": []})
        session.add_all([older, stored])
        session.flush()
        session.add(AgentStep(run_id=older.id, seq=1, round=0, kind="routing", name="escalate_to_ultra",
                              input={"reasons": ["current plan infeasible"]}, output={"tier": "ultra"}))
        session.commit()
        stored_id, older_id = stored.id, older.id

    from app.api.agent import run_out

    assert client.get(f"/api/emails/{demo}/agent").json()["result"]["routing"]["tier"] == "super"
    with session_factory() as session:
        rebuilt = run_out(session, session.get(AgentRun, older_id)).result.routing
    assert rebuilt == {"tier": "ultra", "escalated": True, "reasons": ["current plan infeasible"], "super_attempted": False}
    assert stored_id > older_id


def test_demo_reset_is_off_unless_enabled(client):
    assert client.post("/api/demo/reset").status_code == 403


def test_assessment_in_the_background_can_be_polled(client, session_factory, monkeypatch, demo):  # noqa: F811
    monkeypatch.setattr(agent_api, "SessionLocal", session_factory)
    monkeypatch.setattr(agent_api, "run_agent", functools.partial(run_agent, search=fake_search))

    started = client.post(f"/api/emails/{demo}/agent?background=true").json()

    assert started["status"] in ("running", "completed", "needs_review")
    for _ in range(50):
        run = client.get(f"/api/emails/{demo}/agent").json()
        if run["status"] != "running":
            break
        time.sleep(0.1)
    assert run["status"] in ("completed", "needs_review") and run["steps"]
    with session_factory() as session:
        assert session.query(AgentRun).count() == 1

