"""Fixes made against DEV cases 022+: risk routing, dates, revision suffixes, colour changes,
classification enum, and repeated dates."""

import json
from datetime import UTC, date, datetime

import pytest

from app.agent import routing
from app.agent.loop import run_agent
from app.agent.tools.diff_po_versions import merge_snapshots, plan_versions
from app.llm.router import LLMRouter
from app.models import Email, Order
from app.schemas.extraction import Classification, EmailCategory, POExtraction
from app.schemas.orders import StatedChange
from app.schemas.risk import RiskFlag, RiskReport
from app.services.normalise import (
    clean_colour_name,
    date_convention,
    normalise_extraction,
    removed_colours,
    resolve_date,
    revision_in_text,
    split_letter_suffix,
    split_po_revision,
)
from app.services.orders import record_email_po
from tests.scripted import ScriptedClient, reply
from tests.test_agent import demo, fake_search  # noqa: F401  (fixture)


def _po(**values) -> POExtraction:
    return POExtraction.model_validate(
        {k: {"value": v, "confidence": 0.9, "evidence": str(v)} for k, v in values.items() if k != "line_items"}
        | {"line_items": values.get("line_items", [])}
    )


# --- 2. ambiguous numeric dates --------------------------------------------------------------


@pytest.mark.parametrize(("model_iso", "text", "country", "expected", "ambiguous"), [
    # US: month first, from the country
    ("2027-04-03", "Ex-factory: 03/04/2027", "United States", "2027-03-04", False),
    # EU: day first, from the country
    ("2027-03-05", "Liefertermin: 05.03.2027", "Germany", "2027-03-05", False),
    ("2027-05-03", "Liefertermin: 05.03.2027", "Germany", "2027-03-05", False),
    # AU, two-digit year: day first
    ("2027-03-02", "ex-factory 02/03/27 please", "Australia", "2027-03-02", False),
    ("2027-02-03", "ex-factory 02/03/27 please", "Australia", "2027-03-02", False),
    # JP: year first is unambiguous, left alone
    ("2027-03-05", "Ex-factory: 2027/03/05", "Japan", "2027-03-05", False),
    # ISO: unambiguous, left alone
    ("2027-03-05", "Ex-factory: 2027-03-05", None, "2027-03-05", False),
    # an unambiguous date in the same email settles it, with no country
    ("2027-04-03", "PO date 10/15/2026. Ship 03/04/2027.", None, "2027-03-04", False),
    # no country, no evidence: flagged, not guessed
    ("2027-04-03", "Ship 03/04/2027.", None, "2027-04-03", True),
    # Canada uses both: flagged
    ("2027-04-03", "Ship 03/04/2027.", "Canada", "2027-04-03", True),
    # the email contradicts the country: flagged
    ("2027-04-03", "PO date 10/15/2026. Ship 03/04/2027.", "Germany", "2027-04-03", True),
    # a date written in words is not touched
    ("2027-04-03", "Ship 3 April 2027.", "United States", "2027-04-03", False),
    # day and month equal: nothing to resolve
    ("2027-03-03", "Ship 03/03/2027.", None, "2027-03-03", False),
])
def test_ambiguous_dates(model_iso, text, country, expected, ambiguous):
    assert resolve_date(model_iso, text, date_convention(text, country)) == (expected, ambiguous)


def test_unresolved_delivery_date_is_marked_for_review():
    extraction = _po(delivery_date="2027-04-03")
    notes = normalise_extraction(extraction, "Please ship by 03/04/2027.")

    assert extraction.ambiguous_dates == ["delivery_date"]
    assert extraction.delivery_date.value == date(2027, 4, 3)
    assert "ambiguous" in notes[-1]


def test_resolved_delivery_date_keeps_its_type():
    extraction = _po(delivery_date="2027-04-03", destination_country="USA")
    normalise_extraction(extraction, "Ex-factory 03/04/2027 to our Savannah, GA warehouse")

    assert extraction.delivery_date.value == date(2027, 3, 4) and extraction.ambiguous_dates == []


# --- 3. a date equal to the order's date is no change ------------------------------------------


def test_restated_same_date_on_a_new_order_is_one_version():
    update = {"po_number": "X-1001", "delivery_date": "2027-03-12", "line_items": []}
    stated = [StatedChange(field="delivery_date", old="2027-03-12", new="2027-03-12")]

    assert len(plan_versions(None, update, stated)) == 1


def test_restated_same_date_on_an_order_is_no_version():
    previous = {"po_number": "X-1001", "delivery_date": "2027-03-12", "total_quantity": 1000, "line_items": []}

    assert plan_versions(previous, {"delivery_date": "2027-03-12", "line_items": []}, []) == []


# --- 4. revision suffixes --------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "base", "revision"), [
    ("PRN-2210 Rev A", "PRN-2210", "A"),
    ("PRN-2210 rev. B", "PRN-2210", "B"),
    ("PRN-2210 REVISION 2", "PRN-2210", "2"),
    ("PRN-2210 Amendment 1", "PRN-2210", "1"),
    ("PRN-2210 Amendment No. 3", "PRN-2210", "3"),
    ("PRN-2210 Amdt 4", "PRN-2210", "4"),
    ("PRN-2210-R3", "PRN-2210", "3"),
    ("PRN-2210 (R3)", "PRN-2210", "3"),
    ("PRN-2210 v2", "PRN-2210", "2"),
    ("PRN-2210_v2", "PRN-2210", "2"),
    ("PRN-2210", "PRN-2210", None),
])
def test_revision_suffixes(raw, base, revision):
    assert split_po_revision(raw) == (base, revision)


def test_bare_letter_suffix_is_split_only_on_request():
    assert split_po_revision("PRN-2210-A") == ("PRN-2210-A", None)
    assert split_letter_suffix("PRN-2210-A") == ("PRN-2210", "A")
    assert split_letter_suffix("PO-A") == ("PO-A", None)


def test_revision_dropped_by_the_model_is_recovered_from_the_email():
    extraction = _po(po_number="PRN-2210")
    normalise_extraction(extraction, "Attached is PRN-2210 Rev B with the new sizes.")

    assert (extraction.po_number.value, extraction.po_revision) == ("PRN-2210", "B")
    assert revision_in_text("PRN-2210", "see PRN-2210, page 2") is None


def test_po_with_revision_read_as_style_becomes_the_po():
    extraction = _po(style="PRN-2210 Rev B")
    normalise_extraction(extraction, "")

    assert (extraction.po_number.value, extraction.po_revision, extraction.style.value) == ("PRN-2210", "B", None)


def _email(session, received="2026-10-20") -> Email:
    email = Email(sender="b@x.example", subject="x", body="-",
                  received_at=datetime.fromisoformat(received).replace(tzinfo=UTC))
    session.add(email)
    session.flush()
    return email


def test_bare_letter_suffix_matches_a_known_order(session_factory):
    with session_factory() as session:
        record_email_po(session, _email(session), _po(po_number="PRN-2210", buyer="Pernille A/S",
                        total_quantity=1000, delivery_date="2027-03-12"), [], "")
        extraction = _po(po_number="PRN-2210-A", buyer="Pernille A/S", total_quantity=1200)

        result = record_email_po(session, _email(session), extraction, [], "")

        assert (extraction.po_number.value, extraction.po_revision) == ("PRN-2210", "A")
        assert result.version.version == 2 and session.query(Order).count() == 1


def test_bare_letter_suffix_without_a_known_order_is_kept(session_factory):
    with session_factory() as session:
        extraction = _po(po_number="AB-1001-A", buyer="Someone Ltd")
        record_email_po(session, _email(session), extraction, [], "")

        assert extraction.po_number.value == "AB-1001-A" and extraction.po_revision is None


# --- 5. colour changes ---------------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "clean"), [
    ("Nachtblau to", "Nachtblau"), ("increase Navy", "Navy"), ("Sky Blue", "Sky Blue"),
    ("Navy now", "Navy"), ("to", "to"),
])
def test_colour_names_lose_the_wording_around_them(raw, clean):
    assert clean_colour_name(raw) == clean


@pytest.mark.parametrize(("text", "removed"), [
    ("Please drop Mustard from the order.", ["Mustard"]),
    ("We need to cancel the Sea Mist colour.", ["Sea Mist"]),
    ("Rust is cancelled; Navy stays.", ["Rust"]),
    ("Mustard to 0 pcs, Navy unchanged.", ["Mustard"]),
    ("Please do not cancel Mustard.", []),
    ("Navy to 1,600 pcs.", []),
])
def test_removed_colours(text, removed):
    assert removed_colours(text, ["Mustard", "Navy", "Rust", "Sea Mist"]) == removed


def test_a_dropped_colour_is_recorded_as_a_removal(session_factory):
    with session_factory() as session:
        record_email_po(session, _email(session), _po(po_number="PRN-2210", buyer="Pernille A/S", total_quantity=3000,
                        line_items=[{"colour": "Charcoal", "quantity": 1500}, {"colour": "Mustard", "quantity": 1500}]),
                        [], "")
        extraction = _po(po_number="PRN-2210", line_items=[{"colour": "Charcoal to", "quantity": 1600}])
        normalise_extraction(extraction, "")

        result = record_email_po(session, _email(session), extraction, [],
                                 "Charcoal to 1,600 pcs and please drop Mustard.")

        fields = {c["field"]: (c["old"], c["new"]) for c in result.version.changes}
        assert fields == {"line_items.Charcoal.quantity": (1500, 1600), "line_items.Mustard": (1500, None),
                          "total_quantity": (3000, 1600)}


def test_merge_removes_a_colour_set_to_zero():
    previous = {"total_quantity": 2000, "line_items": [{"colour": "A", "quantity": 1000}, {"colour": "B", "quantity": 1000}]}

    merged = merge_snapshots(previous, {"line_items": [{"colour": "B", "quantity": 0}]})

    assert [i["colour"] for i in merged["line_items"]] == ["A"] and merged["total_quantity"] == 1000


# --- 6. classification enum ---------------------------------------------------------------------------


def test_unknown_intent_becomes_other_and_is_kept():
    c = Classification.model_validate({"category": "order_status", "intents": ["order_status", "payment"],
                                       "has_po_data": False, "summary": "s", "confidence": 0.7})

    assert c.category is EmailCategory.OTHER
    assert c.intents == [EmailCategory.OTHER, EmailCategory.PAYMENT]
    assert c.unrecognised == ["order_status"]


def test_output_schema_constrains_intents_and_hides_internal_fields():
    schema = Classification.output_schema()

    assert "unrecognised" not in schema["properties"]
    enum = schema["$defs"]["EmailCategory"]["enum"]
    assert set(enum) == {c.value for c in EmailCategory}


# --- 1. risk routing ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [
    ("Good news: the fabric is already in-house.", "materials"),
    ("Trims are in stock at your end.", "materials"),
    ("We can accept a partial shipment of 60% by the original date.", "partial"),
    ("OK to ship in two lots.", "partial"),
    ("The fabric is not ready yet.", None),
    ("Fabric ready by 10 Jan.", None),
    ("Please confirm the ex-factory date.", None),
])
def test_feasibility_evidence_in_the_email(text, expected):
    reasons = routing.reasons_before({}, text)
    found = "materials" if any("materials" in r for r in reasons) else "partial" if reasons else None
    assert found == expected


def _flag(severity, category="capacity"):
    return RiskFlag(severity=severity, category=category, reason="r", evidence=["E1"])


@pytest.mark.parametrize(("verdict", "flags", "conflict"), [
    ("feasible", [_flag("high")], True),
    ("tight", [_flag("high", "delivery")], True),
    ("tight", [_flag("medium")], False),
    ("infeasible", [], True),
    ("infeasible", [_flag("high")], False),
    ("feasible", [_flag("high", "price")], False),
])
def test_conflict_with_feasibility(verdict, flags, conflict):
    evidence = {"E1": {"is_current_plan": True, "verdict": verdict}}
    assert (routing.conflict_with_feasibility(RiskReport(summary="s", flags=flags), evidence) is not None) == conflict


def _run(settings, session_factory, email_id, replies, prefetch):
    client = ScriptedClient(replies)
    router = LLMRouter(settings, client=client, session_factory=session_factory)
    with session_factory() as session:
        run = run_agent(session, session.get(Email, email_id), router, search=fake_search, prefetch=prefetch)
        return run, client, list(run.steps)


def test_infeasible_plan_runs_on_ultra_and_says_why(settings, session_factory, demo):  # noqa: F811
    final = reply(json.dumps({"summary": "Infeasible.", "flags": [
        {"severity": "high", "category": "capacity", "reason": "short", "evidence": ["E3"]}]}))

    run, client, steps = _run(settings, session_factory, demo, [final], prefetch=True)

    assert client.requests[0]["model"] == "test/ultra"
    assert run.result["routing"]["tier"] == "ultra" and run.result["routing"]["super_attempted"] is False
    [routing_step] = [s for s in steps if s.kind == "routing"]
    assert "infeasible" in routing_step.summary


def test_invalid_super_report_is_rerun_on_ultra(settings, session_factory, demo):  # noqa: F811
    bad = reply("not json")
    good = reply(json.dumps({"summary": "Fine.", "flags": []}))

    run, client, _ = _run(settings, session_factory, demo, [bad, bad, good], prefetch=False)

    assert [r["model"] for r in client.requests] == ["test/super", "test/super", "test/ultra"]
    assert run.result["routing"]["escalated"] and "validation" in run.result["routing"]["reasons"][0]
    assert run.status == "completed"


def test_ultra_outage_falls_back_to_super(settings, session_factory, demo):  # noqa: F811
    from openai import OpenAIError

    final = reply(json.dumps({"summary": "Infeasible.", "flags": [
        {"severity": "high", "category": "capacity", "reason": "short", "evidence": ["E3"]}]}))
    client = ScriptedClient([final])
    scripted = client.chat.completions.create

    def create(**kwargs):
        if kwargs["model"] == "test/ultra":
            client.requests.append(kwargs)
            raise OpenAIError("<html><head><title>503 Service Temporarily Unavailable</title></head></html>")
        return scripted(**kwargs)

    client.chat.completions.create = create
    router = LLMRouter(settings, client=client, session_factory=session_factory)
    with session_factory() as session:
        run = run_agent(session, session.get(Email, demo), router, search=fake_search, prefetch=True)
        steps = list(run.steps)

    assert [r["model"] for r in client.requests] == ["test/ultra", "test/super"]
    assert run.status == "completed" and run.result["flags"]
    assert run.result["routing"]["tier"] == "super"
    assert "Ultra was unavailable" in run.result["routing"]["fallback"]
    assert "<html" not in run.result["routing"]["fallback"]
    assert "503 Service Temporarily Unavailable" in run.result["routing"]["fallback"]
    assert [s.name for s in steps if s.kind == "routing"] == ["escalate_to_ultra", "ultra_unavailable"]


def test_no_trigger_stays_on_super(settings, session_factory, demo):  # noqa: F811
    run, client, _ = _run(settings, session_factory, demo, [reply(json.dumps({"summary": "Fine.", "flags": []}))],
                          prefetch=False)

    assert [r["model"] for r in client.requests] == ["test/super"]
    assert run.result["routing"] == {"tier": "super", "escalated": False, "reasons": [], "super_attempted": True}


# --- 7. eval oracle --------------------------------------------------------------------------------


def test_oracle_says_yes_only_for_the_linked_order():
    from eval.run_eval import oracle_answer

    order_of_case = {"case_a": 1, "case_b": 2}
    assert oracle_answer({"candidate_order_id": 1}, "case_a", order_of_case) is True
    assert oracle_answer({"candidate_order_id": 2}, "case_a", order_of_case) is False
    assert oracle_answer({"candidate_order_id": 1}, None, order_of_case) is False


def test_restoring_a_colour_name_does_not_bring_back_the_wording_after_it():
    extraction = _po(line_items=[{"colour": "Heather Charcoal to", "quantity": 900}])
    normalise_extraction(extraction, "Two changes: Heather Charcoal to 900 pcs, and drop Mustard Seed.")

    assert [i.colour for i in extraction.line_items] == ["Heather Charcoal"]


# --- unconfirmed (ambiguous) dates never drive a high schedule finding ------------------------------


def test_policy_turns_schedule_findings_on_a_guessed_date_into_one_confirm_flag():
    from app.services.risk_policy import CONFIRM_DATE, apply_policy

    evidence = {
        "E1": {"is_current_plan": True, "verdict": "infeasible", "suggested_severity": "high", "reason": "short"},
        "E2": {"contract_value": None},
    }
    report = RiskReport(summary="s", flags=[_flag("high"), _flag("low", "compliance")])

    result = apply_policy(report, evidence, date_unconfirmed="2027-03-04 or 2027-04-03")

    assert [(f.severity, f.category) for f in result.flags] == [("medium", "delivery")]
    assert result.flags[0].reason.startswith(CONFIRM_DATE)
    assert any("not confirmed" in item.note for item in result.info_checked)


def test_without_an_unconfirmed_date_the_infeasible_plan_stays_high():
    from app.services.risk_policy import apply_policy

    evidence = {"E1": {"is_current_plan": True, "verdict": "infeasible", "suggested_severity": "high", "reason": "short"}}
    assert apply_policy(RiskReport(summary="s"), evidence).flags[0].severity == "high"


def test_infeasible_plan_on_a_guessed_date_does_not_escalate():
    evidence = {"E1": {"is_current_plan": True, "verdict": "infeasible"}}
    assert routing.reasons_before(evidence, "", date_unconfirmed=True) == []
    assert routing.reasons_before(evidence, "") != []


def test_an_ambiguous_date_is_carried_on_the_order_until_stated_clearly(session_factory):
    with session_factory() as session:
        first = _po(po_number="NB-3307", buyer="Northbay Outfitters Ltd", total_quantity=1200, delivery_date="2027-03-04")
        first.ambiguous_dates = ["delivery_date"]
        result = record_email_po(session, _email(session), first, [], "")
        assert result.version.data["date_unconfirmed"] is True

        price_only = _po(po_number="NB-3307", unit_price="8.80")
        assert record_email_po(session, _email(session), price_only, [], "").version.data["date_unconfirmed"] is True

        clear = _po(po_number="NB-3307", delivery_date="2027-04-03")
        assert record_email_po(session, _email(session), clear, [], "Ship 3 April 2027.").version.data["date_unconfirmed"] is False


# --- a status email that mentions the current date is no change ------------------------------------


@pytest.mark.parametrize(("text", "extracted"), [
    ("Is BS-26-0442 still on track for 15/02?", "2026-02-15"),     # partial date, year guessed wrong
    ("Ship 12/03 as planned?", "2027-12-03"),                       # partial date, day and month swapped
    ("Still 15.02.2027 on your side?", "2027-02-15"),               # the same date: no change anyway
])
def test_a_status_email_mentioning_the_current_date_is_no_change(session_factory, text, extracted):
    current = "2027-02-15" if "15" in text else "2027-03-12"
    with session_factory() as session:
        record_email_po(session, _email(session), _po(po_number="BS-26-0442", total_quantity=2400, delivery_date=current), [], "")

        result = record_email_po(session, _email(session), _po(po_number="BS-26-0442", delivery_date=extracted), [], text)

        assert result.version is None or result.version.version == 1
        assert session.query(Order).one().versions[-1].data["delivery_date"] == current


def test_a_real_date_change_is_still_recorded(session_factory):
    with session_factory() as session:
        record_email_po(session, _email(session), _po(po_number="BS-26-0442", total_quantity=2400, delivery_date="2027-02-15"), [], "")

        result = record_email_po(session, _email(session), _po(po_number="BS-26-0442", delivery_date="2027-02-01"), [],
                                 "Please move ex-factory from 15/02 to 01/02.")

        assert [c["field"] for c in result.version.changes] == ["delivery_date"]


def test_ambiguous_date_in_a_follow_up_is_read_with_the_order_country(session_factory):
    with session_factory() as session:
        record_email_po(session, _email(session), _po(po_number="PCS-4410", total_quantity=1800,
                        delivery_date="2027-04-05", destination_country="United States"), [], "")
        follow_up = _po(po_number="PCS-4410", delivery_date="2027-05-04")
        follow_up.ambiguous_dates = ["delivery_date"]

        result = record_email_po(session, _email(session), follow_up, [], "the ship date stays 04/05/2027 on our side")

        assert follow_up.ambiguous_dates == [] and result.version is None
        assert session.query(Order).one().versions[-1].data.get("date_unconfirmed") in (None, False)


def test_fact_check_reads_year_first_dates():
    from app.services.fact_check import fact_check

    assert fact_check("Balance by 23 Apr 2027.", {}, "the balance by 2027/04/23")["violations"] == []
