import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from openai import OpenAIError
from sqlalchemy import select

from app.agent.loop import MAX_ROUNDS, run_agent
from app.api import rate_limit
from app.db import get_session
from app.llm.router import LLMRouter, get_router
from app.main import app
from app.models import AgentStep, Email, LLMCall
from app.schemas.extraction import POExtraction
from app.services import tavily_client
from app.services.orders import record_po_version
from tests.scripted import ScriptedClient, reply


def fake_search(query, max_results=4):
    return tavily_client.SearchResponse(
        query=query,
        answer="Fibre composition labels are required.",
        hits=[tavily_client.SearchHit(title="Textile labelling", url="https://example.eu/textile-labels",
                                      content="Labels must state fibre composition.")],
    )


def _email(session, po, qty, delivery, received, destination="Germany", subject="PO"):
    values = {"po_number": po, "buyer": "Nordwind Mode GmbH", "total_quantity": qty,
              "delivery_date": delivery, "destination_country": destination, "currency": "USD",
              "unit_price": "4.85"}
    extraction = POExtraction.model_validate(
        {name: {"value": value, "confidence": 0.9, "evidence": str(value)} for name, value in values.items()}
    )
    email = Email(
        sender="anna@nordwind.example", subject=subject, body="See attached PO.",
        received_at=datetime.fromisoformat(received).replace(tzinfo=UTC),
        classification={"category": "new_po", "intents": ["new_po"], "has_po_data": True,
                        "summary": "Order.", "confidence": 0.9},
        extraction={"fields": extraction.model_dump(mode="json"), "review": [], "escalations": []},
    )
    session.add(email)
    session.flush()
    record_po_version(session, email, extraction, [])
    session.commit()
    return email


@pytest.fixture
def demo(session_factory):
    """case_001 -> case_002 in miniature, plus a competing order due before the new date."""
    with session_factory() as session:
        _email(session, "NW-45120", 12000, "2026-12-15", "2026-09-01")
        _email(session, "BP-778455", 8400, "2026-11-20", "2026-09-15", destination="United States")
        revised = _email(session, "NW-45120", 13500, "2026-11-30", "2026-09-18", subject="Revised PO")
        return revised.id


def _mock_router(settings, session_factory):
    settings.llm_mode = "mock"
    return LLMRouter(settings, session_factory=session_factory)


def test_pulled_forward_revision_is_flagged_high_with_evidence(settings, session_factory, demo):
    with session_factory() as session:
        email = session.get(Email, demo)
        run = run_agent(session, email, _mock_router(settings, session_factory), search=fake_search)

        assert run.status == "completed"
        prefetched = [(s.name, s.evidence_id) for s in run.steps if s.kind == "tool" and s.round == 0]
        assert prefetched == [
            ("find_order", "E1"), ("diff_po_versions", "E2"), ("check_delivery_feasibility", "E3"),
            ("check_delivery_feasibility", "E4"), ("propose_delivery_options", "E5"),
        ]
        current, previous = (s for s in run.steps if s.name == "check_delivery_feasibility")
        assert current.output["verdict"] == "infeasible" and current.output["other_orders_load"] == 8400
        assert previous.output["delivery_date"] == "2026-12-15" and previous.output["verdict"] == "feasible"
        # In the loop the planner only had the optional tools.
        assert [s.name for s in run.steps if s.kind == "tool" and s.round > 0] == ["check_compliance"]

        flags = run.result["flags"]
        capacity = next(f for f in flags if f["category"] == "capacity")
        assert (capacity["severity"], capacity["evidence"], capacity["verified"]) == ("high", ["E3"], True)
        value = next(f for f in flags if f["category"] == "price")
        assert (value["severity"], value["source"], value["evidence"]) == ("high", "rule", ["E2"])
        assert "+12.5%" in value["reason"]
        assert any(f["category"] == "delivery" for f in flags)
        # Background compliance results are info, not a flag.
        assert not any(f["category"] == "compliance" for f in flags)
        assert "https://example.eu/textile-labels" in run.result["info_checked"][0]["evidence"]


def test_delivery_options_find_the_earliest_feasible_date_and_a_split(settings, session_factory, demo):
    with session_factory() as session:
        run = run_agent(session, session.get(Email, demo), _mock_router(settings, session_factory), search=fake_search)
        options = next(s for s in run.steps if s.name == "propose_delivery_options").output

    assert options["options_needed"] is True
    assert options["requested_date"] == "2026-11-30" and options["quantity"] == 13500
    earliest = options["earliest_feasible_date_full_quantity"]
    assert "2026-11-30" < earliest <= "2026-12-31"
    split = options["partial_shipment"]
    # 9,314 pcs of capacity remain by 30 Nov, rounded down to 9,300
    assert (split["quantity_on_requested_date"], split["balance_quantity"]) == (9300, 4200)
    assert split["balance_date"] == earliest


def test_every_model_call_is_logged_against_the_run(settings, session_factory, demo):
    with session_factory() as session:
        run = run_agent(session, session.get(Email, demo), _mock_router(settings, session_factory), search=fake_search)
        calls = session.scalars(select(LLMCall).where(LLMCall.run_id == run.id)).all()
        llm_steps = [s for s in run.steps if s.kind == "llm"]

        assert calls and all(call.tier == "ultra" for call in calls)
        assert {s.call_id for s in llm_steps} == {c.id for c in calls}


def _scripted_run(settings, session_factory, email_id, replies, default=None, prefetch=False):
    client = ScriptedClient(replies, default=default)
    router = LLMRouter(settings, client=client, session_factory=session_factory)
    with session_factory() as session:
        run = run_agent(session, session.get(Email, email_id), router, search=fake_search, prefetch=prefetch)
        return run, client, list(run.steps)


def test_with_prefetch_ultra_can_answer_in_one_call(settings, session_factory, demo):
    final = reply(json.dumps({"summary": "Revision is infeasible.", "flags": [
        {"severity": "high", "category": "capacity", "reason": "4,186 pcs short by 30 Nov.", "evidence": ["E3"]},
    ]}))

    run, client, steps = _scripted_run(settings, session_factory, demo, [final], prefetch=True)

    assert len(client.requests) == 1
    request = client.requests[0]
    assert {t["function"]["name"] for t in request["tools"]} == {
        "check_compliance", "lookup_buyer", "check_delivery_feasibility"
    }
    observation = json.loads(request["messages"][1]["content"])
    assert [item["tool"] for item in observation["prefetched_evidence"]][:3] == [
        "find_order", "diff_po_versions", "check_delivery_feasibility"
    ]
    assert run.result["flags"][0]["evidence"] == ["E3"]


def test_with_prefetch_the_order_tools_are_not_offered_again(settings, session_factory, demo):
    replies = [
        reply(tool_calls=[("find_order", {"po_number": "NW-45120"}), ("diff_po_versions", {"order_id": 1, "from_version": 1, "to_version": 2})]),
        reply(json.dumps({"summary": "Done.", "flags": []})),
    ]

    run, _, steps = _scripted_run(settings, session_factory, demo, replies, prefetch=True)

    loop_steps = [s for s in steps if s.kind == "tool" and s.round == 1]
    # find_order with the same arguments is a repeat of E1; the diff was pre-fetched too
    assert loop_steps[0].output["duplicate_of"] == "E1"
    assert loop_steps[1].output["duplicate_of"] == "E2"


def test_hard_cap_of_eight_tool_rounds(settings, session_factory, demo):
    looping = reply(tool_calls=[("find_order", {"po_number": "NW-45120"})])
    final = reply(json.dumps({"summary": "Done.", "flags": []}))
    replies = [reply(tool_calls=[("find_order", {"po_number": f"NW-{i}"})]) for i in range(MAX_ROUNDS)]

    run, client, steps = _scripted_run(settings, session_factory, demo, replies + [final], default=looping)

    assert run.rounds == MAX_ROUNDS
    assert len([s for s in steps if s.kind == "tool"]) == MAX_ROUNDS
    # 8 planning calls with tools, then one final call without tools
    assert len(client.requests) == MAX_ROUNDS + 1
    assert "tools" not in client.requests[-1]
    assert all(request["max_tokens"] > 0 for request in client.requests)


def test_invented_evidence_is_dropped_and_missing_high_risk_is_added(settings, session_factory, demo):
    with session_factory() as session:
        order_id = session.get(Email, demo).order_id
    replies = [
        reply(tool_calls=[("check_delivery_feasibility", {"order_id": order_id})]),
        reply(json.dumps({"summary": "Looks fine.", "flags": [
            {"severity": "low", "category": "quantity", "reason": "Quantity looks fine.",
             "evidence": ["E9", "https://made-up.example"]},
        ]})),
    ]

    run, _, _ = _scripted_run(settings, session_factory, demo, replies)

    assert not any(f["category"] == "quantity" for f in run.result["flags"])
    demoted = run.result["info_checked"][0]
    assert demoted["evidence"] == [] and "no verifiable evidence" in demoted["note"]
    rule_flag = run.result["flags"][0]
    assert (rule_flag["severity"], rule_flag["source"], rule_flag["evidence"]) == ("high", "rule", ["E1"])


def test_invalid_final_answer_is_retried_once_without_thinking(settings, session_factory, demo):
    replies = [reply("I think it is fine."), reply(json.dumps({"summary": "Fine.", "flags": []}))]

    run, client, _ = _scripted_run(settings, session_factory, demo, replies)

    assert run.status == "completed"
    assert client.requests[1]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert client.requests[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}


def test_failed_model_call_ends_the_run_cleanly(settings, session_factory, demo):
    class Failing(ScriptedClient):
        def _create(self, **kwargs):
            raise OpenAIError("upstream unavailable")

    router = LLMRouter(settings, client=Failing([]), session_factory=session_factory)
    with session_factory() as session:
        run = run_agent(session, session.get(Email, demo), router, search=fake_search)

    assert run.status == "failed"
    assert "upstream unavailable" in run.error


def test_repeated_identical_call_is_answered_from_the_earlier_result(settings, session_factory, demo):
    replies = [
        reply(tool_calls=[("find_order", {"po_number": "NW-45120"})]),
        reply(tool_calls=[("find_order", {"po_number": "NW-45120"})]),
        reply(json.dumps({"summary": "Done.", "flags": []})),
    ]

    run, _, steps = _scripted_run(settings, session_factory, demo, replies)

    tool_steps = [s for s in steps if s.kind == "tool"]
    assert tool_steps[1].output == {"evidence_id": "E2", "duplicate_of": "E1", "note": "Same call already made; use E1."}
    assert tool_steps[1].summary == "Repeat of E1, not run again"


def test_tool_errors_are_returned_to_the_model(settings, session_factory, demo):
    replies = [
        reply(tool_calls=[("diff_po_versions", {"order_id": 999, "from_version": 1, "to_version": 2}),
                          ("no_such_tool", {})]),
        reply(json.dumps({"summary": "Could not check.", "flags": []})),
    ]

    run, client, steps = _scripted_run(settings, session_factory, demo, replies)

    tool_steps = [s for s in steps if s.kind == "tool"]
    assert "No order with id 999" in tool_steps[0].output["error"]
    assert "Unknown tool" in tool_steps[1].output["error"]
    tool_messages = [m for m in client.requests[1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 2


# --- API ---------------------------------------------------------------------------------


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


def test_agent_api_runs_and_returns_the_trace(client, demo, monkeypatch):
    monkeypatch.setattr(tavily_client, "search", fake_search)
    assert client.get(f"/api/emails/{demo}/agent").status_code == 404

    body = client.post(f"/api/emails/{demo}/agent").json()

    assert body["status"] == "completed"
    assert body["result"]["flags"][0]["severity"] == "high"
    assert body["ultra_calls"] >= 2
    llm_step = next(s for s in body["steps"] if s["kind"] == "llm")
    assert llm_step["tier"] == "ultra" and llm_step["model"] == "test/ultra"
    tool_step = next(s for s in body["steps"] if s["kind"] == "tool")
    assert tool_step["evidence_id"] == "E1" and tool_step["summary"]

    again = client.post(f"/api/emails/{demo}/agent").json()
    assert again["id"] == body["id"]
    assert again["notice"] == "Showing the stored risk assessment."
    assert client.get(f"/api/emails/{demo}/agent").json()["id"] == body["id"]


def test_agent_api_needs_an_order(client, session_factory):
    with session_factory() as session:
        email = Email(sender="a@b.example", subject="Status?", body="Where is my shipment?")
        session.add(email)
        session.commit()
        email_id = email.id

    response = client.post(f"/api/emails/{email_id}/agent")

    assert response.status_code == 400
    assert session_factory().scalar(select(AgentStep)) is None
