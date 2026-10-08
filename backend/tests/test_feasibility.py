from datetime import date

from app.agent.tools.feasibility import check_feasibility
from app.services.profiles import list_profiles, load_profile

TIRUPPUR = load_profile("india_tiruppur")
DHAKA = load_profile("bangladesh_dhaka")
AS_OF = date(2026, 9, 18)


def test_profiles_load():
    assert {p.id for p in list_profiles()} >= {"india_tiruppur", "bangladesh_dhaka"}
    assert TIRUPPUR.capacity.pcs_per_week == 10000


def test_revised_po_pulled_forward_is_infeasible():
    # case_002: 13,500 pcs now due 30 Nov; another order of 8,400 pcs is due before then.
    result = check_feasibility(quantity=13500, delivery_date=date(2026, 11, 30), as_of=AS_OF,
                               profile=TIRUPPUR, other_orders_load=8400)

    assert result.verdict == "infeasible"
    assert result.suggested_severity == "high"
    assert result.production_days_available == 31  # 73 days minus 42 days of fabric
    assert result.free_capacity_per_week == 4000
    assert result.capacity_in_window == 17714
    assert result.shortfall_pcs == 13500 - (17714 - 8400)
    assert "short" in result.reason


def test_original_po_date_was_feasible():
    # case_001's plan: 12,000 pcs by 15 Dec.
    result = check_feasibility(quantity=12000, delivery_date=date(2026, 12, 15), as_of=AS_OF,
                               profile=TIRUPPUR, other_orders_load=8400)

    assert result.verdict == "feasible"
    assert result.suggested_severity == "low"
    assert result.slack_days >= TIRUPPUR.thresholds.min_slack_days


def test_same_order_is_feasible_for_the_dhaka_profile():
    result = check_feasibility(quantity=13500, delivery_date=date(2026, 11, 30), as_of=AS_OF,
                               profile=DHAKA, other_orders_load=8400)

    assert result.verdict == "feasible"


def test_not_enough_time_after_fabric_lead_time():
    result = check_feasibility(quantity=500, delivery_date=date(2026, 11, 5), as_of=AS_OF, profile=TIRUPPUR)

    assert result.verdict == "infeasible"
    assert "fabric lead time" in result.reason


def test_fabric_in_house_removes_the_fabric_lead_time():
    result = check_feasibility(quantity=9000, delivery_date=date(2026, 11, 10), as_of=date(2026, 9, 20),
                               profile=TIRUPPUR, fabric_ready=True)

    assert result.fabric_days == 0
    assert result.verdict == "feasible"


def test_tight_when_most_free_capacity_is_used():
    result = check_feasibility(quantity=15000, delivery_date=date(2026, 12, 15), as_of=AS_OF,
                               profile=TIRUPPUR, other_orders_load=8400)

    assert result.verdict == "tight"
    assert result.suggested_severity == "medium"
