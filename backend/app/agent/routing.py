"""When the risk agent runs on Ultra instead of Super.

Super is the default. A run goes to Ultra when:

- before the run:
  - the current plan is infeasible, so delivery options need weighing;
  - the email or its thread contains evidence that could change feasibility
    (fabric or trims already in-house, a partial or split shipment offered);
- after Super's run:
  - Super's flags conflict with the Python feasibility result;
  - Super's report failed validation, even after the retry.

The reasons are recorded as a "routing" step in the agent trace, in the run's result,
and in the `detail` of each Ultra call in the LLM call log.
"""

import re
from typing import Any

from app.schemas.risk import RiskReport

_SCHEDULE_CATEGORIES = {"delivery", "capacity"}
# Fabric, yarn or trims already available: the fabric lead time may not apply.
_MATERIAL = r"(?:fabric|fabrics|yarn|greige|trims?|accessories|materials?)"
_AVAILABLE = (
    r"(?:in[- ]house|in stock|on hand|(?:already\s+)?(?:here|available|received|arrived|knitted|dyed|booked|in the factory)"
    r"|ready(?!\s+(?:by|on|in)\b))"
)
_MATERIAL_READY = re.compile(
    rf"\b{_MATERIAL}\b[^.\n]{{0,40}}?\b(?:is|are|was|were|has been|have been|now|already)?\s*{_AVAILABLE}"
    rf"|\b{_AVAILABLE}\s+{_MATERIAL}\b",
    re.IGNORECASE,
)
_PARTIAL_SHIPMENT = re.compile(
    r"\b(?:partial|part|split)[- ](?:shipments?|deliver(?:y|ies)|shipping|ship)\b"
    r"|\bship(?:ping)?\s+(?:it\s+)?in\s+(?:two|2|three|3)\s+(?:lots|batches|parts|shipments)\b"
    r"|\bpart[- ]ship\b",
    re.IGNORECASE,
)
_NEGATED = re.compile(r"\b(?:not|no|isn't|aren't|wasn't|won't|cannot|can't|never)\b[^.\n]{0,20}$", re.IGNORECASE)


def _found(pattern: re.Pattern, text: str) -> str | None:
    """The first match not preceded by a negation in the same clause ("fabric is not ready")."""
    for match in pattern.finditer(text):
        before = text[max(0, match.start() - 30): match.start()]
        if not _NEGATED.search(before) and not re.search(r"\b(?:not|n't)\b", match.group(0), re.IGNORECASE):
            return match.group(0).strip()
    return None


def current_plan(evidence: dict[str, dict]) -> dict | None:
    return next((r for r in evidence.values() if r.get("is_current_plan")), None)


def reasons_before(evidence: dict[str, dict], email_text: str) -> list[str]:
    """Triggers known before the model runs."""
    reasons = []
    plan = current_plan(evidence)
    if plan and plan.get("verdict") == "infeasible":
        reasons.append("current plan infeasible: delivery options need weighing")
    if quote := _found(_MATERIAL_READY, email_text):
        reasons.append(f"thread says materials are available ('{quote}'): may change feasibility")
    if quote := _found(_PARTIAL_SHIPMENT, email_text):
        reasons.append(f"partial shipment mentioned ('{quote}'): may change feasibility")
    return reasons


def conflict_with_feasibility(report: RiskReport, evidence: dict[str, dict]) -> str | None:
    """Super's raw flags (before the policy) against the Python feasibility verdict."""
    plan = current_plan(evidence)
    if not plan or plan.get("verdict") not in {"feasible", "tight", "infeasible"}:
        return None
    schedule_flags = [f for f in report.flags if f.category in _SCHEDULE_CATEGORIES]
    if plan["verdict"] == "infeasible" and not schedule_flags:
        return "Super raised no delivery or capacity flag, but the feasibility check says infeasible"
    if plan["verdict"] != "infeasible" and any(f.severity == "high" for f in schedule_flags):
        return f"Super raised a high delivery or capacity flag, but the feasibility check says {plan['verdict']}"
    return None


def routing_record(tier: str, reasons: list[str], super_attempted: bool) -> dict[str, Any]:
    return {"tier": tier, "escalated": tier == "ultra", "reasons": reasons, "super_attempted": super_attempted}
