from app.agent.tools.agent_tools import ToolContext, run_tool
from app.schemas.risk import RiskFlag, RiskReport
from app.services import tavily_client
from app.services.profiles import load_profile
from app.services.risk_policy import apply_policy, contract_value_change

URL = "https://eur-lex.example/textile-labelling"
EVIDENCE = {
    "E1": {"evidence_id": "E1", "is_current_plan": True, "verdict": "infeasible", "suggested_severity": "high",
           "reason": "4,186 pcs short."},
    "E2": {"evidence_id": "E2", "changes": [], "alerts": [],
           "contract_value": {"old_value": "58200.00", "new_value": "65475.00", "change": "7275.00",
                              "change_pct": 12.5, "currency": "USD"}},
    "E3": {"evidence_id": "E3", "sources": [{"url": URL, "title": "EU 1007/2011"}]},
    "E4": {"evidence_id": "E4", "is_current_plan": True, "verdict": "feasible", "suggested_severity": "low",
           "reason": "Feasible."},
}


def _flag(**values) -> RiskFlag:
    return RiskFlag.model_validate({"severity": "medium", "category": "other", "reason": "r", **values})


def _apply(*flags: RiskFlag) -> RiskReport:
    return apply_policy(RiskReport(summary="s", flags=list(flags)), EVIDENCE)


def _by_category(report: RiskReport, category: str) -> RiskFlag | None:
    return next((f for f in report.flags if f.category == category), None)


def test_compliance_flag_needs_a_concrete_rule_and_a_url():
    vague = _apply(_flag(category="compliance", reason="Germany has strict labelling rules.", evidence=["E3", URL]))
    no_url = _apply(_flag(category="compliance", reason="Fibre labels required.", rule="EU 1007/2011", evidence=["E3"]))
    concrete = _apply(_flag(category="compliance", reason="Fibre composition label required.",
                            rule="EU Regulation 1007/2011, Art. 14", evidence=["E3", URL]))

    assert _by_category(vague, "compliance") is None
    assert vague.info_checked[0].note == "Not a flag: no concrete rule with a source URL."
    assert _by_category(no_url, "compliance") is None
    assert _by_category(concrete, "compliance").rule == "EU Regulation 1007/2011, Art. 14"


def test_buyer_flag_needs_an_adverse_finding():
    sparse = _apply(_flag(category="buyer", reason="Little public information.", evidence=[URL]))
    adverse = _apply(_flag(category="buyer", reason="Insolvency filing.", adverse_finding="Filed for insolvency 2026-08",
                           evidence=[URL]))

    assert _by_category(sparse, "buyer") is None and sparse.info_checked[0].topic == "buyer"
    assert _by_category(adverse, "buyer") is not None


def test_high_needs_a_matching_finding():
    report = _apply(
        _flag(severity="high", category="data_quality", reason="Missing style.", evidence=["E4"]),
        _flag(severity="low", category="capacity", reason="Capacity issue.", evidence=["E1"]),
        _flag(severity="high", category="delivery", reason="Feasible plan.", evidence=["E4"]),
    )

    data = _by_category(report, "data_quality")
    assert (data.severity, data.severity_adjusted_from) == ("medium", "high")
    # The model's low flag on an infeasible plan is not upgraded; the rule adds the high finding,
    # and merging folds the model's wording into it.
    capacity = _by_category(report, "capacity")
    assert (capacity.severity, capacity.reason, capacity.related) == ("high", "4,186 pcs short.", ["Capacity issue."])
    assert _by_category(report, "delivery").severity == "medium"


def test_large_contract_value_change_is_always_high():
    report = _apply()

    value = _by_category(report, "price")
    assert (value.severity, value.source, value.evidence) == ("high", "rule", ["E2"])
    assert "+12.5%" in value.reason
    assert _by_category(report, "capacity").source == "rule"


def test_contract_value_change():
    old = {"total_quantity": 6800, "unit_price": "2.95", "currency": "GBP"}
    new = {"total_quantity": 6800, "unit_price": "2.80", "currency": "GBP"}

    change = contract_value_change(old, new)

    assert change == {"old_value": "20060.00", "new_value": "19040.00", "change": "-1020.00",
                      "change_pct": -5.1, "currency": "GBP"}
    assert contract_value_change(old, old) is None
    assert contract_value_change({"total_quantity": 10}, new) is None


def test_long_reasons_are_cut_to_one_line():
    flag = _flag(reason="word " * 100)

    assert len(flag.reason) <= 300 and flag.reason.endswith("...")


def test_search_cache_key_is_normalised(session_factory):
    calls = []

    def search(query, max_results=4):
        calls.append(query)
        return tavily_client.SearchResponse(query=query, answer="a", hits=[])

    with session_factory() as session:
        ctx = ToolContext(session=session, as_of=None, profile=load_profile("india_tiruppur"), search=search)
        run_tool(ctx, "check_compliance", '{"destination_country": "Germany", "product": "Men\'s T-shirt"}')
        _, second, _ = run_tool(ctx, "check_compliance", '{"destination_country": " germany ", "product": "mens t shirt"}')
        ctx.calls.clear()
        run_tool(ctx, "lookup_buyer", '{"company_name": "Nordwind Mode GmbH"}')
        _, buyer_again, _ = run_tool(ctx, "lookup_buyer", '{"company_name": "NORDWIND MODE"}')

    assert len(calls) == 2
    assert second["cached"] is True and buyer_again["cached"] is True


def test_flags_are_merged_to_one_per_category():
    report = _apply(
        _flag(severity="medium", category="delivery", reason="Pulled forward 14 days.", evidence=["E2"]),
        _flag(severity="high", category="delivery", reason="New date infeasible.", evidence=["E1"]),
        _flag(severity="low", category="delivery", reason="Old date also tight.", evidence=["E1", "E4"]),
        _flag(severity="medium", category="compliance", reason="Fibre labels.", rule="EU 1007/2011", evidence=["E3", URL]),
        _flag(severity="medium", category="compliance", reason="Care labels.", rule="DIN EN ISO 3758", evidence=[URL]),
    )

    categories = [f.category for f in report.flags]
    assert len(categories) == len(set(categories))
    delivery = _by_category(report, "delivery")
    assert (delivery.severity, delivery.reason) == ("high", "New date infeasible.")
    assert delivery.evidence == ["E1", "E2", "E4"]
    assert delivery.related == ["Pulled forward 14 days.", "Old date also tight."]
    compliance = _by_category(report, "compliance")
    assert compliance.related == ["Care labels."] and compliance.evidence == ["E3", URL]


def test_merged_flag_keeps_the_models_wording_over_a_rule():
    report = _apply(_flag(severity="high", category="capacity", reason="Short by 4,186 pcs.", evidence=["E1"]))

    [capacity] = [f for f in report.flags if f.category == "capacity"]
    assert (capacity.reason, capacity.source) == ("Short by 4,186 pcs.", "model")


def test_fabric_ready_check_supersedes_the_default_current_plan_check():
    evidence = EVIDENCE | {
        "E5": {"evidence_id": "E5", "is_current_plan": True, "fabric_ready": True, "verdict": "feasible",
               "suggested_severity": "low", "reason": "Feasible with fabric in-house."},
    }
    report = apply_policy(RiskReport(summary="s", flags=[
        _flag(severity="high", category="delivery", reason="Infeasible.", evidence=["E1"]),
    ]), evidence)

    delivery = _by_category(report, "delivery")
    assert (delivery.severity, delivery.severity_adjusted_from) == ("medium", "high")
    assert _by_category(report, "capacity") is None
