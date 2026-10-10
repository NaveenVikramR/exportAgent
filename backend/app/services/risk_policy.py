"""The flag policy from backend/policy/risk_policy.yaml, applied to the agent's report.

The model proposes flags; Python decides what remains a flag, and how severe:
- evidence must point at a real tool result or a URL a tool returned;
- a compliance flag needs a concrete rule and a source URL;
- a buyer flag needs an adverse finding and a source URL;
- high is only for an infeasible plan or a contract value change above the threshold;
- anything that falls short moves to "Info checked";
- finally, flags are merged to one per category.
"""

from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

import yaml
from pydantic import BaseModel

from app.config import BACKEND_DIR
from app.schemas.orders import DELIVERY_PULLED_FORWARD
from app.schemas.risk import InfoItem, RiskFlag, RiskReport

POLICY_PATH = BACKEND_DIR / "policy" / "risk_policy.yaml"
_RANK = {"low": 0, "medium": 1, "high": 2}


class SeverityPolicy(BaseModel):
    high_contract_value_change_pct: float
    high_contract_value_change_abs: float


class FlagPolicy(BaseModel):
    compliance_requires_rule_and_url: bool
    buyer_requires_adverse_finding_and_url: bool


class DeliveryOptionsPolicy(BaseModel):
    search_days: int
    partial_round_to: int


class RiskPolicy(BaseModel):
    severity: SeverityPolicy
    flags: FlagPolicy
    delivery_options: DeliveryOptionsPolicy


@lru_cache
def load_policy() -> RiskPolicy:
    return RiskPolicy.model_validate(yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")))


def _value(snapshot: dict[str, Any]) -> Decimal | None:
    try:
        return Decimal(str(snapshot["total_quantity"])) * Decimal(str(snapshot["unit_price"]))
    except (KeyError, TypeError, InvalidOperation):
        return None


def contract_value_change(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any] | None:
    """Order value (quantity x unit price) before and after, or None if either is unknown."""
    before, after = _value(old), _value(new)
    if before is None or after is None or before == 0 or before == after:
        return None
    delta = after - before
    return {
        "old_value": str(before.quantize(Decimal("0.01"))),
        "new_value": str(after.quantize(Decimal("0.01"))),
        "change": str(delta.quantize(Decimal("0.01"))),
        "change_pct": float(round(delta / before * 100, 1)),
        "currency": new.get("currency") or old.get("currency"),
    }


def is_high_value_change(change: dict[str, Any], policy: RiskPolicy) -> bool:
    return (
        abs(change["change_pct"]) > policy.severity.high_contract_value_change_pct
        or abs(Decimal(change["change"])) > Decimal(str(policy.severity.high_contract_value_change_abs))
    )


def _urls(evidence: dict[str, dict]) -> set[str]:
    return {
        source["url"]
        for result in evidence.values()
        for source in result.get("sources", [])
        if source.get("url")
    }


def current_plan_checks(evidence: dict[str, dict]) -> dict[str, dict]:
    """Feasibility results for the order's current date and quantity.

    A check run with fabric_ready=true (the email says fabric is already in-house)
    supersedes the default check, which assumes the fabric lead time still applies.
    """
    current = {eid: r for eid, r in evidence.items() if r.get("is_current_plan") and "verdict" in r}
    if any(r.get("fabric_ready") for r in current.values()):
        current = {eid: r for eid, r in current.items() if r.get("fabric_ready")}
    return current


def apply_policy(report: RiskReport, evidence: dict[str, dict], policy: RiskPolicy | None = None) -> RiskReport:
    policy = policy or load_policy()
    urls = _urls(evidence)
    current = current_plan_checks(evidence)
    infeasible = {eid for eid, r in current.items() if r["verdict"] == "infeasible"}
    high_value = {eid for eid, r in evidence.items()
                  if r.get("contract_value") and is_high_value_change(r["contract_value"], policy)}

    flags: list[RiskFlag] = []
    info = list(report.info_checked)
    for flag in report.flags:
        flag.evidence = [item for item in flag.evidence if item in evidence or item in urls]
        flag.verified = bool(flag.evidence)
        cited_urls = [item for item in flag.evidence if item in urls]

        reason_to_demote = None
        if not flag.verified:
            reason_to_demote = "no verifiable evidence"
        elif flag.category == "compliance" and policy.flags.compliance_requires_rule_and_url \
                and not (flag.rule and cited_urls):
            reason_to_demote = "no concrete rule with a source URL"
        elif flag.category == "buyer" and policy.flags.buyer_requires_adverse_finding_and_url \
                and not (flag.adverse_finding and cited_urls):
            reason_to_demote = "no adverse finding with a source URL"
        if reason_to_demote:
            info.append(InfoItem(topic=flag.category, finding=flag.reason, evidence=flag.evidence,
                                 note=f"Not a flag: {reason_to_demote}."))
            continue

        # High needs a matching finding: infeasibility for delivery/capacity, a large value change for price/quantity.
        # Lower severities are left alone; the rules below make sure every high finding has a high flag.
        cited = set(flag.evidence)
        backs_high = (flag.category in ("delivery", "capacity") and bool(cited & infeasible)) or (
            flag.category in ("price", "quantity") and bool(cited & high_value)
        )
        if flag.severity == "high" and not backs_high:
            flag.severity_adjusted_from, flag.severity = "high", "medium"
        flags.append(flag)

    def covered(eid: str, minimum: str) -> bool:
        return any(eid in f.evidence and _RANK[f.severity] >= _RANK[minimum] for f in flags)

    # Findings that must never be missing, whatever the model concluded.
    for eid, result in evidence.items():
        if eid in current and result.get("verdict") in ("infeasible", "tight") \
                and not covered(eid, result["suggested_severity"]):
            flags.append(RiskFlag(severity=result["suggested_severity"], category="capacity",
                                  reason=result["reason"], evidence=[eid], verified=True, source="rule"))
        if eid in high_value and not covered(eid, "high"):
            change = result["contract_value"]
            flags.append(RiskFlag(
                severity="high", category="price", evidence=[eid], verified=True, source="rule",
                reason=(f"Contract value {change['old_value']} → {change['new_value']} {change['currency'] or ''} "
                        f"({change['change_pct']:+}%).").replace("  ", " ").replace(" (", " ("),
            ))
        if DELIVERY_PULLED_FORWARD in result.get("alerts", []) and not covered(eid, "medium"):
            change = next((c for c in result.get("changes", []) if c.get("alert") == DELIVERY_PULLED_FORWARD), None)
            flags.append(RiskFlag(
                severity="medium", category="delivery", evidence=[eid], verified=True, source="rule",
                reason=change["detail"] if change else "Delivery date pulled forward in the latest PO version.",
            ))

    return RiskReport(summary=report.summary, flags=merge_flags(flags), info_checked=info)


def merge_flags(flags: list[RiskFlag]) -> list[RiskFlag]:
    """One flag per category: the most severe finding leads, the others become related notes.

    Evidence is combined; a merged flag counts as from the model if any of its findings was.
    """
    groups: dict[str, list[RiskFlag]] = {}
    for flag in flags:
        groups.setdefault(flag.category, []).append(flag)
    merged = []
    for group in groups.values():
        # Most severe first; among equals, the model's own wording before a rule's.
        group.sort(key=lambda f: (-_RANK[f.severity], f.source == "rule"))
        lead = group[0].model_copy(deep=True)
        for other in group[1:]:
            lead.evidence += [item for item in other.evidence if item not in lead.evidence]
            if other.reason != lead.reason and other.reason not in lead.related:
                lead.related.append(other.reason)
            lead.rule = lead.rule or other.rule
            lead.adverse_finding = lead.adverse_finding or other.adverse_finding
        lead.verified = any(f.verified for f in group)
        lead.source = "model" if any(f.source == "model" for f in group) else "rule"
        merged.append(lead)
    merged.sort(key=lambda f: -_RANK[f.severity])
    return merged
