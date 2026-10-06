from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.llm.router import LLMRouter, get_router
from app.main import app
from app.models import LLMCall


@pytest.fixture
def client(session_factory, settings):
    def override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_router] = lambda: LLMRouter(settings, session_factory=session_factory)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_reports_database_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_routes_lists_every_task_type(client):
    body = client.get("/api/trace/routes").json()

    assert {row["task_type"] for row in body} >= {"classify", "draft_reply", "planning"}
    assert all(row["model"] for row in body)


def test_summary_aggregates_calls_per_model(client, session_factory):
    with session_factory() as session:
        session.add_all(
            [
                LLMCall(task_type="classify", tier="nano", model="m/nano", input_tokens=100,
                        output_tokens=10, latency_ms=200, cost_usd=Decimal("0.00001")),
                LLMCall(task_type="extract", tier="nano", model="m/nano", input_tokens=300,
                        output_tokens=30, latency_ms=400, cost_usd=Decimal("0.00003")),
                LLMCall(task_type="planning", tier="ultra", model="m/ultra", input_tokens=50,
                        output_tokens=5, latency_ms=900, cost_usd=Decimal("0.00007")),
            ]
        )
        session.commit()

    body = client.get("/api/trace/summary").json()

    assert body["total_calls"] == 3
    assert Decimal(body["spent_today_usd"]) == Decimal("0.00011")
    assert Decimal(body["daily_spend_cap_usd"]) == Decimal("1.00")
    assert Decimal(body["total_cost_usd"]) == Decimal("0.00011")
    nano = next(row for row in body["by_model"] if row["model"] == "m/nano")
    assert nano["calls"] == 2
    assert nano["input_tokens"] == 400
    assert nano["avg_latency_ms"] == 300

    calls = client.get("/api/trace/calls", params={"limit": 2}).json()
    assert len(calls) == 2
    assert calls[0]["model"] == "m/ultra"
