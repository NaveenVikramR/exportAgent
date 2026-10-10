import json

import pytest
from fastapi.testclient import TestClient

from app.agent.loop import run_agent
from app.api import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, get_router
from app.main import app
from app.models import Email
from app.services.drafting import build_facts
from app.services.fact_check import fact_check
from tests.scripted import ScriptedClient, reply
from tests.test_agent import demo, fake_search  # noqa: F401  (pytest fixture and helper)

FACTS = {"order": {"delivery_date": "2026-11-30", "total_quantity": 13500, "unit_price": "4.85"},
         "delivery_options": {"earliest_feasible_date_full_quantity": "2026-12-08",
                              "partial_shipment": {"quantity_on_requested_date": 9300, "balance_quantity": 4200}}}
SOURCE = "Delivery Date (ex-factory): 30 November 2026. Unit Price: 4.85 per piece."


# --- fact check -------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "by 30 November 2026", "by November 30, 2026", "by 30/11/2026", "by 2026-11-30", "by 30th Nov", "by Dec 8",
    "9,300 pcs now and 4,200 pieces later", "13,500 units", "USD 4.85 per piece", "$4.85", "4.85 each",
])
def test_values_from_the_sources_pass(text):
    assert fact_check(text, FACTS, SOURCE)["violations"] == []


@pytest.mark.parametrize(("text", "kind"), [
    ("by 15 December 2026", "date"), ("by Dec 15", "date"), ("by 2026-12-15", "date"),
    ("500 pcs", "quantity"), ("13,000", "quantity"),
    ("USD 4.70", "price"), ("€6.40", "price"), ("4.70 per piece", "price"), ("a total of 65,475.00", "price"),
])
def test_invented_values_are_flagged(text, kind):
    [violation] = fact_check(text, FACTS, SOURCE)["violations"]

    assert violation["kind"] == kind


def test_each_value_is_checked_once():
    result = fact_check("Ship 9,300 pcs on 2026-11-30 at USD 4.85.", FACTS, SOURCE)

    assert (result["checked"], result["violations"]) == (3, [])


# --- drafting -----------------------------------------------------------------------------


def _mock_router(settings, session_factory):
    return LLMRouter(settings.model_copy(update={"llm_mode": "mock"}), session_factory=session_factory)


def _assessed(settings, session_factory, email_id):
    with session_factory() as session:
        run_agent(session, session.get(Email, email_id), _mock_router(settings, session_factory), search=fake_search)


def test_facts_include_delivery_options_but_not_other_buyers_orders(settings, session_factory, demo):
    _assessed(settings, session_factory, demo)
    with session_factory() as session:
        facts = build_facts(session, session.get(Email, demo))

    assert facts["delivery_check"]["current_plan"]["verdict"] == "infeasible"
    assert facts["delivery_options"]["partial_shipment"]["quantity_on_requested_date"] == 9300
    assert facts["contract_value"]["change_pct"] == 12.5
    assert facts["order"]["total_quantity"] == 13500 and facts["previous_version"]["total_quantity"] == 12000
    # The competing order belongs to another buyer and must not reach the reply.
    assert "BP-778455" not in json.dumps(facts)


@pytest.fixture
def client(session_factory, settings):
    def override():
        with session_factory() as session:
            yield session

    rate_limit.reset()
    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
    rate_limit.reset()


def _use_router(settings, session_factory, client_=None):
    router = LLMRouter(settings, client=client_, session_factory=session_factory)
    app.dependency_overrides[get_router] = lambda: router
    return router


def test_drafting_needs_a_risk_assessment_first(client, settings, session_factory, demo):
    _use_router(settings, session_factory)

    response = client.post(f"/api/emails/{demo}/drafts")

    assert response.status_code == 400
    assert "Assess the order" in response.json()["detail"]


def test_mock_drafts_propose_the_computed_options_and_pass_the_check(client, settings, session_factory, demo):
    _assessed(settings, session_factory, demo)
    settings.llm_mode = "mock"
    _use_router(settings, session_factory)

    drafts = client.post(f"/api/emails/{demo}/drafts").json()

    reply_draft = next(d for d in drafts if d["kind"] == "buyer_reply")
    assert {d["kind"] for d in drafts} == {"buyer_reply", "internal_note"}
    assert "9300 pcs by 2026-11-30" in reply_draft["text"]
    assert reply_draft["violations"] == [] and reply_draft["checked"] > 0
    assert reply_draft["subject"].startswith("Re: ")
    # Asking again returns the pending drafts instead of drafting again.
    assert [d["id"] for d in client.post(f"/api/emails/{demo}/drafts").json()] == [d["id"] for d in drafts]


def test_super_writes_with_thinking_on_and_violations_block_approval(client, settings, session_factory, demo):
    _assessed(settings, session_factory, demo)
    invented = "We can ship all 13,500 pcs by 20 December 2026 at USD 4.70.\n\nKarthik"
    scripted = ScriptedClient([reply(invented), reply("- Note for production.")])
    _use_router(settings, session_factory, scripted)

    drafts = client.post(f"/api/emails/{demo}/drafts").json()

    assert scripted.requests[0]["model"] == "test/super"
    assert scripted.requests[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}
    reply_draft = next(d for d in drafts if d["kind"] == "buyer_reply")
    assert {v["text"] for v in reply_draft["violations"]} == {"20 December 2026", "USD 4.70"}
    assert reply_draft["model"] == "test/super"

    blocked = client.post(f"/api/drafts/{reply_draft['id']}/approve", json={"reviewer": "Karthik"})
    assert blocked.status_code == 409

    edited = client.patch(f"/api/drafts/{reply_draft['id']}",
                          json={"body": "We can ship 9,300 pcs by 30 November 2026 at USD 4.85.\n\nKarthik"}).json()
    assert edited["violations"] == [] and edited["text"].startswith("We can ship 9,300")

    sent = client.post(f"/api/drafts/{reply_draft['id']}/approve", json={"reviewer": "Karthik"}).json()
    assert (sent["status"], sent["reviewed_by"]) == ("sent", "Karthik")
    assert sent["sent_at"] is not None and sent["reviewed_at"] is not None
    assert client.get(f"/api/emails/{demo}").json()["status"] == "replied"
    assert client.post(f"/api/drafts/{reply_draft['id']}/approve", json={"reviewer": "x"}).status_code == 409


def test_violations_can_be_acknowledged_and_drafts_rejected(client, settings, session_factory, demo):
    _assessed(settings, session_factory, demo)
    _use_router(settings, session_factory, ScriptedClient([reply("Ship 500 pcs."), reply("- Note.")]))
    reply_draft, note = client.post(f"/api/emails/{demo}/drafts").json()

    sent = client.post(f"/api/drafts/{reply_draft['id']}/approve",
                       json={"reviewer": "Karthik", "acknowledge_violations": True}).json()
    rejected = client.post(f"/api/drafts/{note['id']}/reject", json={"reviewer": "Priya", "reason": "Too vague"}).json()

    assert sent["status"] == "sent"
    assert (rejected["status"], rejected["reject_reason"], rejected["reviewed_by"]) == ("rejected", "Too vague", "Priya")
    assert client.get("/api/drafts").json() == []
    assert len(client.get("/api/drafts", params={"draft_status": "sent"}).json()) == 1


def test_empty_draft_is_retried_without_thinking(client, settings, session_factory, demo):
    _assessed(settings, session_factory, demo)
    scripted = ScriptedClient([reply(""), reply("Thank you for PO NW-45120."), reply("- Note.")])
    _use_router(settings, session_factory, scripted)

    drafts = client.post(f"/api/emails/{demo}/drafts").json()

    assert drafts[0]["text"] == "Thank you for PO NW-45120."
    assert scripted.requests[1]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_force_supersedes_pending_drafts(client, settings, session_factory, demo):
    _assessed(settings, session_factory, demo)
    settings.llm_mode = "mock"
    _use_router(settings, session_factory)
    first = client.post(f"/api/emails/{demo}/drafts").json()

    second = client.post(f"/api/emails/{demo}/drafts", params={"force": True}).json()

    assert {d["id"] for d in first}.isdisjoint({d["id"] for d in second})
    assert {d["id"] for d in client.get(f"/api/emails/{demo}/drafts").json()} == {d["id"] for d in second}


def test_typographic_thousands_separators_are_read_as_numbers():
    text = "Ship 9 300 pcs on 30 Nov 2026 and 4 200 pieces later; NW‑45120."

    assert fact_check(text, FACTS, SOURCE)["violations"] == []
    assert fact_check("Ship 9 400 pcs.", FACTS, SOURCE)["violations"][0]["text"] == "9,400 pcs"
