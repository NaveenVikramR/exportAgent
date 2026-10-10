"""Template stand-in for the Super drafting calls (LLM_MODE=mock). Uses only values from FACTS."""

import json
from typing import Any


def _facts(messages: list[dict[str, Any]]) -> dict[str, Any]:
    content = messages[-1]["content"]
    if "FACTS:\n" not in content or "\n\nBUYER EMAIL:" not in content:
        return {"factory": {"name": "the factory", "contact_name": "Merchandiser", "contact_role": "Merchandiser"}}
    start =content.index("FACTS:\n") + len("FACTS:\n")
    end = content.index("\n\nBUYER EMAIL:")
    return json.loads(content[start:end])


def mock_reply(messages: list[dict[str, Any]]) -> str:
    facts = _facts(messages)
    factory, order = facts["factory"], facts.get("order") or {}
    po = order.get("po_number") or "your order"
    lines = ["Dear Sir/Madam,", "", f"Thank you for your email regarding {po}."]
    plan = (facts.get("delivery_check") or {}).get("current_plan")
    options = facts.get("delivery_options")
    if plan and plan["verdict"] == "infeasible" and options:
        lines.append(f"We cannot complete {plan['quantity']} pcs by {plan['delivery_date']}.")
        if options.get("earliest_feasible_date_full_quantity"):
            lines.append(f"We can ship the full quantity by {options['earliest_feasible_date_full_quantity']}.")
        split = options.get("partial_shipment")
        if split:
            lines.append(f"Alternatively {split['quantity_on_requested_date']} pcs by {split['requested_date']} "
                         f"and {split['balance_quantity']} pcs by {split['balance_date']}.")
    elif order.get("delivery_date"):
        lines.append(f"We confirm the delivery date of {order['delivery_date']}.")
    for item in facts.get("missing_information", []):
        lines.append(f"Please confirm the {item}.")
    lines += ["", "Best regards,", factory["contact_name"], f"{factory['contact_role']}, {factory['name']}"]
    return "\n".join(lines)


def mock_note(messages: list[dict[str, Any]]) -> str:
    facts = _facts(messages)
    order = facts.get("order") or {}
    lines = [f"- PO {order.get('po_number')}: {order.get('total_quantity')} pcs, delivery {order.get('delivery_date')}."]
    lines += [f"- {flag['severity'].upper()}: {flag['reason']}" for flag in facts.get("risk_flags", [])]
    lines.append("- Hold fabric booking until the buyer confirms.")
    return "\n".join(lines)
