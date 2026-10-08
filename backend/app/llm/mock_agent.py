"""Rule-based stand-in for the Ultra planner (LLM_MODE=mock).

A fixed policy: find the order, diff the last two versions, check feasibility,
check compliance, then write flags straight from the tool results. It exists so
the agent loop, tools and trace can run without a key; it does not reason.
"""

import json
from typing import Any

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}


def _tool_results(messages: list[dict[str, Any]]) -> dict[str, list[dict]]:
    names = {
        call["id"]: call["function"]["name"]
        for message in messages if message.get("tool_calls")
        for call in message["tool_calls"]
    }
    results: dict[str, list[dict]] = {}
    for message in messages:
        if message.get("role") == "tool":
            results.setdefault(names.get(message["tool_call_id"], "?"), []).append(json.loads(message["content"]))
    return results


def _call(name: str, n: int, **arguments: Any) -> dict[str, Any]:
    return {"id": f"mock_{name}_{n}", "name": name, "arguments": json.dumps(arguments)}


def _final(observation: dict, done: dict[str, list[dict]]) -> dict[str, Any]:
    flags = []
    for result in done.get("check_delivery_feasibility", []):
        if result.get("verdict") in ("tight", "infeasible"):
            flags.append({"severity": result["suggested_severity"], "category": "capacity",
                          "reason": result["reason"], "evidence": [result["evidence_id"]]})
    for result in done.get("diff_po_versions", []):
        for change in result.get("changes", []):
            if change.get("alert"):
                flags.append({"severity": "medium", "category": "delivery",
                              "reason": change["detail"], "evidence": [result["evidence_id"]]})
    for result in done.get("check_compliance", []):
        if result.get("sources"):
            flags.append({"severity": "low", "category": "compliance",
                          "reason": f"Confirm labelling requirements for {observation['extracted'].get('destination_country')}.",
                          "evidence": [result["evidence_id"], result["sources"][0]["url"]]})
    flags.sort(key=lambda flag: -_SEVERITY_RANK[flag["severity"]])
    return {"content": json.dumps({"summary": "Mock risk assessment built from the tool results.", "flags": flags})}


def mock_plan(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
    observation = json.loads(messages[1]["content"])
    done = _tool_results(messages)
    if not tools:
        return _final(observation, done)

    po_number = observation["extracted"].get("po_number")
    if "find_order" not in done and po_number:
        return {"content": None, "tool_calls": [_call("find_order", 1, po_number=po_number)]}

    calls = []
    order = (done.get("find_order") or [{}])[-1]
    if order.get("found"):
        versions = order["versions"]
        if len(versions) >= 2 and "diff_po_versions" not in done:
            calls.append(_call("diff_po_versions", 1, order_id=order["order_id"],
                               from_version=versions[-2]["version"], to_version=versions[-1]["version"]))
        if versions[-1].get("delivery_date") and versions[-1].get("total_quantity") \
                and "check_delivery_feasibility" not in done:
            calls.append(_call("check_delivery_feasibility", 1, order_id=order["order_id"]))
    destination = observation["extracted"].get("destination_country")
    if destination and "check_compliance" not in done:
        calls.append(_call("check_compliance", 1, destination_country=destination, product="knitted apparel"))
    if calls:
        return {"content": None, "tool_calls": calls}
    return _final(observation, done)
