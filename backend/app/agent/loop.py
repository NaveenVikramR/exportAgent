"""The risk agent: observe -> reason -> act (tools) -> feed back, at most 8 tool rounds.

With pre-fetch (the default), Python first runs the deterministic checks:
find the order, diff the last two versions, check delivery feasibility for the
current and the previous plan, and propose delivery options if the plan is
infeasible. The model receives those results as evidence and keeps the loop only
for the optional tools (compliance, buyer lookup, a what-if feasibility check) and
the final judgement. Afterwards the flag policy (app/services/risk_policy.py)
decides what stays a flag and corrects severities to the rubric.

The model is Super by default; the run goes to Ultra on the triggers in
app/agent/routing.py (before the run, or after Super's answer), and the reason is
logged as a "routing" step.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent import routing
from app.agent.tools.agent_tools import LOOP_TOOL_SPECS, TOOL_NAMES, TOOL_SPECS, ToolContext, run_tool
from app.config import get_settings
from app.llm.prompts import planner as prompt
from app.llm.router import LLMError, LLMResult, LLMRouter, SpendCapExceeded
from app.llm.structured import json_block
from app.llm.tasks import TaskType, Tier
from app.models import AgentRun, AgentStep, Email, Order
from app.schemas.risk import RiskReport
from app.services import tavily_client
from app.services.profiles import load_profile
from app.services.risk_policy import apply_policy

MAX_ROUNDS = 8
PLANNER_MAX_TOKENS = 4000
FINAL_MAX_TOKENS = 2000
_EXCERPT = 1200
# How much of the email the planner sees: enough for the garment and any thread context.
_BODY_CHARS = 1500
_ATTACHMENT_CHARS = 800


def build_observation(email: Email, order: Order | None) -> dict[str, Any]:
    """What the agent sees first: the analysed email and the matched order."""
    extraction = email.extraction or {}
    fields = extraction.get("fields") or {}
    observation: dict[str, Any] = {
        "as_of": email.received_at.date().isoformat(),
        "email": {
            "from": email.sender,
            "subject": email.subject,
            "classification": email.classification,
            "body": email.body[:_BODY_CHARS],
            "attachments": [
                {"filename": a.filename, "text": (a.text_content or "")[:_ATTACHMENT_CHARS]}
                for a in email.attachments
            ],
        },
        "extracted": {
            name: value.get("value") if isinstance(value, dict) else value
            for name, value in fields.items() if name != "line_items"
        },
        "line_items": fields.get("line_items", []),
        "fields_needing_review": [
            f"{flag['field']}: {flag['detail']}" for flag in extraction.get("review", [])
        ],
        "order": None,
    }
    if order is not None:
        latest = order.versions[-1]
        observation["order"] = {
            "order_id": order.id,
            "po_number": order.po_number,
            "current_version": order.current_version,
            "latest_changes": latest.changes or [],
            "factory_profile": order.profile,
        }
    return observation


def _tool_call_message(result: LLMResult) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": result.content or "",
        "tool_calls": [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in result.tool_calls
        ],
    }


def _canonical_arguments(arguments: str) -> str:
    try:
        return json.dumps(json.loads(arguments or "{}"), sort_keys=True)
    except json.JSONDecodeError:
        return arguments


def _parse_report(text: str | None) -> RiskReport:
    return RiskReport.model_validate_json(json_block(text or ""))


def prefetch_calls(order: Order) -> list[tuple[str, dict[str, Any]]]:
    """The deterministic checks every order gets, before the model is involved."""
    lookup = {"po_number": order.po_number} if order.po_number else {"order_id": order.id}
    calls: list[tuple[str, dict[str, Any]]] = [("find_order", lookup)]
    versions = order.versions
    current = versions[-1].data
    if len(versions) >= 2:
        calls.append(("diff_po_versions", {"order_id": order.id, "from_version": versions[-2].version,
                                           "to_version": versions[-1].version}))
    if current.get("delivery_date") and current.get("total_quantity"):
        calls.append(("check_delivery_feasibility", {"order_id": order.id}))
        previous = versions[-2].data if len(versions) >= 2 else None
        if previous and previous.get("delivery_date") and previous.get("total_quantity") and (
            previous["delivery_date"] != current["delivery_date"]
            or previous["total_quantity"] != current["total_quantity"]
        ):
            calls.append(("check_delivery_feasibility", {
                "order_id": order.id, "delivery_date": previous["delivery_date"],
                "quantity": previous["total_quantity"],
            }))
    return calls


def email_text(email: Email) -> str:
    from app.services.analysis import email_text as render

    return render(email)


def run_agent(
    session: Session,
    email: Email,
    router: LLMRouter,
    *,
    search: Callable[..., tavily_client.SearchResponse] | None = None,
    prefetch: bool | None = None,
) -> AgentRun:
    order = email.order
    profile = load_profile(order.profile if order else get_settings().factory_profile)
    run = AgentRun(email_id=email.id, order_id=order.id if order else None, status="running")
    session.add(run)
    session.commit()

    ctx = ToolContext(
        session=session, as_of=email.received_at.date(), profile=profile,
        search=search or tavily_client.search,
    )
    prefetch = get_settings().agent_prefetch if prefetch is None else prefetch
    seq = 0
    evidence: dict[str, dict] = {}
    # (tool, arguments) -> evidence id, so a repeated call is answered from the earlier result
    seen_calls: dict[tuple[str, str], str] = {}

    def add_step(**fields: Any) -> None:
        nonlocal seq
        seq += 1
        session.add(AgentStep(run_id=run.id, seq=seq, **fields))
        session.commit()

    def llm_step(round_: int, name: str, result: LLMResult) -> None:
        add_step(
            round=round_, kind="llm", name=name, call_id=result.call_id,
            input={"task": result.task.value},
            output={
                "content": (result.content or "")[:_EXCERPT],
                "reasoning": (result.reasoning or "")[:_EXCERPT],
                "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in result.tool_calls],
            },
            summary=(
                "Calls " + ", ".join(c.name for c in result.tool_calls) if result.tool_calls
                else "Rewrites the report as valid JSON (thinking off)" if name == "final_retry"
                else "Writes the risk report"
            ),
        )

    def record_tool(round_: int, name: str, args_json: str) -> dict:
        eid = f"E{len(evidence) + 1}"
        args, output, summary = run_tool(ctx, name, args_json)
        output = {"evidence_id": eid, **output}
        evidence[eid] = output
        add_step(round=round_, kind="tool", name=name, input=args, output=output,
                 summary=summary, evidence_id=eid)
        return output

    observation = build_observation(email, order)
    offered = TOOL_SPECS
    if prefetch and order is not None:
        prefetched = []
        for name, args in prefetch_calls(order):
            seen_calls[(name, _canonical_arguments(json.dumps(args)))] = f"E{len(evidence) + 1}"
            prefetched.append({"tool": name, "arguments": args, "result": record_tool(0, name, json.dumps(args))})
        current_plan = next((r for r in evidence.values() if r.get("is_current_plan")), None)
        if current_plan and current_plan.get("verdict") == "infeasible":
            args = {"order_id": order.id}
            prefetched.append({"tool": "propose_delivery_options", "arguments": args,
                               "result": record_tool(0, "propose_delivery_options", json.dumps(args))})
        observation["prefetched_evidence"] = prefetched
        offered = LOOP_TOOL_SPECS
    offered_names = {spec["function"]["name"] for spec in offered}
    base_messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt.system_prompt(prefetched=prefetch and order is not None)},
        {"role": "user", "content": json.dumps(observation, default=str)},
    ]
    prefetched_calls = dict(seen_calls)

    def assess(tier: Tier | None, detail: str | None) -> tuple[RiskReport | None, str | None]:
        """One full reasoning pass. Returns (report, None), or (None, validation error)."""
        messages = list(base_messages)
        seen_calls.clear()
        seen_calls.update(prefetched_calls)
        final: LLMResult | None = None
        for round_ in range(1, MAX_ROUNDS + 1):
            result = router.complete(
                TaskType.PLANNING, messages, max_tokens=PLANNER_MAX_TOKENS, tools=offered,
                reasoning=True, run_id=run.id, tier=tier, detail=detail,
            )
            llm_step(round_, "plan", result)
            if not result.tool_calls:
                final = result
                break
            run.rounds = round_
            messages.append(_tool_call_message(result))
            for call in result.tool_calls:
                eid = f"E{len(evidence) + 1}"
                key = (call.name, _canonical_arguments(call.arguments))
                if key in seen_calls:
                    earlier = seen_calls[key]
                    args = json.loads(key[1]) if key[1] else {}
                    output = {"duplicate_of": earlier, "note": f"Same call already made; use {earlier}."}
                    summary = f"Repeat of {earlier}, not run again"
                elif call.name in TOOL_NAMES and call.name not in offered_names:
                    args = {}
                    output = {"error": f"{call.name} is not available here; its result is already in the pre-fetched evidence."}
                    summary = f"error: {call.name} not offered (pre-fetched)"
                else:
                    seen_calls[key] = eid
                    args, output, summary = run_tool(ctx, call.name, call.arguments)
                output = {"evidence_id": eid, **output}
                evidence[eid] = output
                add_step(round=round_, kind="tool", name=call.name, input=args, output=output,
                         summary=summary, evidence_id=eid)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(output, default=str)})

        if final is None:
            messages.append({"role": "user", "content": prompt.FINAL_ANSWER})
            final = router.complete(TaskType.RISK_REASONING, messages, max_tokens=FINAL_MAX_TOKENS,
                                    reasoning=True, run_id=run.id, tier=tier, detail=detail)
            llm_step(MAX_ROUNDS + 1, "final", final)

        try:
            return _parse_report(final.content), None
        except ValidationError as exc:
            # One retry without thinking, so the budget goes to the answer.
            messages += [
                {"role": "assistant", "content": final.content or ""},
                {"role": "user", "content": prompt.FIX_JSON.format(error=str(exc)[:300])},
            ]
            retry = router.complete(TaskType.RISK_REASONING, messages, max_tokens=FINAL_MAX_TOKENS,
                                    reasoning=False, run_id=run.id, tier=tier, detail=detail)
            llm_step(run.rounds + 1, "final_retry", retry)
            try:
                return _parse_report(retry.content), None
            except ValidationError as retry_exc:
                return None, str(retry_exc)[:1000]

    def route_to_ultra(reasons: list[str]) -> None:
        add_step(round=0, kind="routing", name="escalate_to_ultra", input={"reasons": reasons},
                 output={"tier": "ultra"}, summary="Escalated to Ultra: " + "; ".join(reasons))

    escalate = router.settings.risk_escalation_enabled and order is not None
    reasons = routing.reasons_before(evidence, email_text(email)) if escalate else []
    super_attempted = False
    try:
        if reasons:
            route_to_ultra(reasons)
            report, error = assess(Tier.ULTRA, "ultra escalation: " + "; ".join(reasons))
        else:
            super_attempted = True
            report, error = assess(None, None)
            if escalate:
                after = ([f"Super's report failed validation: {error[:200]}"] if report is None
                         else [c] if (c := routing.conflict_with_feasibility(report, evidence)) else [])
                if after:
                    reasons = after
                    route_to_ultra(reasons)
                    report, error = assess(Tier.ULTRA, "ultra escalation: " + "; ".join(reasons))
        if report is None:
            report = RiskReport(summary="The agent did not return a valid risk report; review manually.")
            run.error = error

    except LLMError as exc:
        run.status = "failed"
        run.error = str(exc)[:1000]
        run.finished_at = datetime.now(UTC)
        session.commit()
        if isinstance(exc, SpendCapExceeded):
            raise
        return run

    report = apply_policy(report, evidence)
    tier_used = "ultra" if reasons else router.tier_for(TaskType.PLANNING).value
    run.result = report.model_dump(mode="json") | {
        "routing": routing.routing_record(tier_used, reasons, super_attempted)
    }
    run.status = "needs_review" if run.error else "completed"
    run.finished_at = datetime.now(UTC)
    session.commit()
    return run
