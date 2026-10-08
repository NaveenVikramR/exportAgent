"""Can the factory make this quantity by this date? Pure Python, all the maths here.

Model: production can start once fabric is ready (fabric lead time after the
as-of date, unless fabric is already in-house). From then until ex-factory the
factory has its free capacity (weekly capacity minus the share already booked
outside ExportAgent), shared with other ExportAgent orders due in the same window.
"""

from dataclasses import asdict, dataclass
from datetime import date
from math import ceil

from app.services.profiles import FactoryProfile


@dataclass(frozen=True)
class Feasibility:
    verdict: str  # feasible | tight | infeasible
    suggested_severity: str  # low | medium | high
    reason: str
    as_of: str
    delivery_date: str
    quantity: int
    days_to_delivery: int
    fabric_days: int
    production_days_available: int
    free_capacity_per_week: int
    capacity_in_window: int
    other_orders_load: int
    capacity_left_for_order: int
    utilisation: float | None
    production_days_needed: int
    slack_days: int
    shortfall_pcs: int

    def to_dict(self) -> dict:
        return asdict(self)


_SEVERITY = {"feasible": "low", "tight": "medium", "infeasible": "high"}


def check_feasibility(
    *,
    quantity: int,
    delivery_date: date,
    as_of: date,
    profile: FactoryProfile,
    other_orders_load: int = 0,
    fabric_ready: bool = False,
) -> Feasibility:
    days_to_delivery = (delivery_date - as_of).days
    fabric_days = 0 if fabric_ready else profile.lead_times.fabric_days
    window = max(days_to_delivery - fabric_days, 0)

    free_per_week = round(profile.capacity.pcs_per_week * (1 - profile.capacity.baseline_utilisation))
    free_per_day = free_per_week / 7
    capacity_in_window = int(window * free_per_day)
    left_for_order = capacity_in_window - other_orders_load
    utilisation = round((quantity + other_orders_load) / capacity_in_window, 3) if capacity_in_window else None
    days_needed = max(ceil((quantity + other_orders_load) / free_per_day), profile.lead_times.min_production_days)
    slack = window - days_needed
    shortfall = max(quantity - max(left_for_order, 0), 0)

    if window < profile.lead_times.min_production_days:
        verdict = "infeasible"
        reason = (
            f"Only {window} production days after the {fabric_days}-day fabric lead time; "
            f"the minimum is {profile.lead_times.min_production_days}."
        )
    elif shortfall > 0:
        verdict = "infeasible"
        reason = (
            f"{quantity:,} pcs needed but only {max(left_for_order, 0):,} pcs of free capacity remain "
            f"before {delivery_date.isoformat()} after other orders ({shortfall:,} pcs short)."
        )
    elif (utilisation or 0) >= profile.thresholds.tight_utilisation or slack < profile.thresholds.min_slack_days:
        verdict = "tight"
        reason = f"Feasible but tight: {utilisation:.0%} of free capacity used, {slack} days of slack."
    else:
        verdict = "feasible"
        reason = f"Feasible: {utilisation:.0%} of free capacity used, {slack} days of slack."

    return Feasibility(
        verdict=verdict,
        suggested_severity=_SEVERITY[verdict],
        reason=reason,
        as_of=as_of.isoformat(),
        delivery_date=delivery_date.isoformat(),
        quantity=quantity,
        days_to_delivery=days_to_delivery,
        fabric_days=fabric_days,
        production_days_available=window,
        free_capacity_per_week=free_per_week,
        capacity_in_window=capacity_in_window,
        other_orders_load=other_orders_load,
        capacity_left_for_order=left_for_order,
        utilisation=utilisation,
        production_days_needed=days_needed,
        slack_days=slack,
        shortfall_pcs=shortfall,
    )
