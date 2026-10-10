"""Rule-based stand-in for the Ultra planner (LLM_MODE=mock).

A fixed policy: use the pre-fetched evidence if there is any, otherwise find the
order, diff the last two versions and check feasibility; check compliance; then
write flags straight from the results. It exists so the agent loop, tools and
trace can run without a key; it does not reason.
"""

import json
from typing import Any

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}


def _tool_results(messages: list[dict[str, Any]], observation: dict) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {}
    for item in observation.get("prefetched_evidence", []):
        results.setdefault(item["tool"], []).append(item["result"])
    names = {
        call["id"]: call["function"]["name"]
        for message in messages if message.get("tool_calls")
        for call in message["tool_calls"]
    }
    for message in messages:
        if message.get("role") == "tool":
            results.setdefault(names.get(message["tool_call_id"], "?"), []).append(json.loads(message["content"]))
    return results


def _call(name: str, n: int, **arguments: Any) -> dict[str, Any]:
    return {"id": f"mock_{name}_{n}", "name": name, "arguments": json.dumps(arguments)}


def _final(observation: dict, done: dict[str, list[dict]]) -> dict[str, Any]:
    flags, info = [], []
    for result in done.get("check_delivery_feasibility", []):
        if result.get("is_current_plan") and result.get("verdict") in ("tight", "infeasible"):
            flags.append({"severity": result["suggested_severity"], "category": "capacity",
                          "reason": result["reason"], "evidence": [result["evidence_id"]]})
    for result in done.get("diff_po_versions", []):
        for change in result.get("changes", []):
            if change.get("alert"):
                flags.append({"severity": "medium", "category": "delivery",
                              "reason": change["detail"], "evidence": [result["evidence_id"]]})
    for result in done.get("check_compliance", []):
        if result.get("sources"):
            info.append({"topic": "compliance",
                         "finding": f"Import rules checked for {observation['extracted'].get('destination_country')}.",
                         "evidence": [result["evidence_id"], result["sources"][0]["url"]]})
    flags.sort(key=lambda flag: -_SEVERITY_RANK[flag["severity"]])
    report = {"summary": "Mock risk assessment built from the tool results.", "flags": flags, "info_checked": info}
    return {"content": json.dumps(report)}


def mock_plan(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
    observation = json.loads(messages[1]["content"])
    done = _tool_results(messages, observation)
    if not tools:
        return _final(observation, done)
    offered = {tool["function"]["name"] for tool in tools}

    po_number = observation["extracted"].get("po_number")
    if "find_order" in offered and "find_order" not in done and po_number:
        return {"content": None, "tool_calls": [_call("find_order", 1, po_number=po_number)]}

    calls = []
    order = (done.get("find_order") or [{}])[-1]
    if order.get("found"):
        versions = order["versions"]
        if "diff_po_versions" in offered and len(versions) >= 2 and "diff_po_versions" not in done:
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
