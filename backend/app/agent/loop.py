"""The risk agent: observe -> reason (Ultra) -> act (tools) -> feed back, at most 8 tool rounds.

Ultra plans and writes the risk report with reasoning on; the tools do every
calculation. After the run, Python checks each flag's evidence against the
tool results, and safety rules add any high-risk finding the model left out.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.tools.agent_tools import TOOL_SPECS, ToolContext, run_tool
from app.config import get_settings
from app.llm.prompts import planner as prompt
from app.llm.router import LLMError, LLMResult, LLMRouter, SpendCapExceeded
from app.llm.structured import json_block
from app.llm.tasks import TaskType
from app.models import AgentRun, AgentStep, Email, Order
from app.schemas.orders import DELIVERY_PULLED_FORWARD
from app.schemas.risk import RiskFlag, RiskReport
from app.services import tavily_client
from app.services.profiles import load_profile

MAX_ROUNDS = 8
PLANNER_MAX_TOKENS = 4000
FINAL_MAX_TOKENS = 2000
_EXCERPT = 1200
# How much of the email the planner sees: enough for the garment and any thread context.
_BODY_CHARS = 1500
_ATTACHMENT_CHARS = 800
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}


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
            name: value.get("value") for name, value in fields.items() if name != "line_items"
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


def _verify_evidence(report: RiskReport, evidence: dict[str, dict]) -> None:
    """Keep only evidence that points at a tool result or a URL a tool returned."""
    urls = {
        source["url"]
        for result in evidence.values()
        for source in result.get("sources", [])
        if source.get("url")
    }
    for flag in report.flags:
        flag.evidence = [item for item in flag.evidence if item in evidence or item in urls]
        flag.verified = bool(flag.evidence)


def _apply_safety_rules(report: RiskReport, evidence: dict[str, dict]) -> None:
    """Findings that must never be missing, whatever the model concluded."""
    def covered(eid: str, minimum: str) -> bool:
        return any(eid in flag.evidence and _SEVERITY_RANK[flag.severity] >= _SEVERITY_RANK[minimum]
                   for flag in report.flags)

    for eid, result in evidence.items():
        if result.get("is_current_plan") and result.get("verdict") in ("infeasible", "tight"):
            severity = result["suggested_severity"]
            if not covered(eid, severity):
                report.flags.append(RiskFlag(
                    severity=severity, category="capacity", reason=result["reason"],
                    evidence=[eid], verified=True, source="rule",
                ))
        if DELIVERY_PULLED_FORWARD in result.get("alerts", []) and not covered(eid, "medium"):
            change = next((c for c in result.get("changes", []) if c.get("alert") == DELIVERY_PULLED_FORWARD), None)
            reason = change["detail"] if change else "Delivery date pulled forward in the latest PO version."
            report.flags.append(RiskFlag(
                severity="medium", category="delivery", reason=reason,
                evidence=[eid], verified=True, source="rule",
            ))
    report.flags.sort(key=lambda flag: -_SEVERITY_RANK[flag.severity])


def run_agent(
    session: Session,
    email: Email,
    router: LLMRouter,
    *,
    search: Callable[..., tavily_client.SearchResponse] | None = None,
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
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt.SYSTEM},
        {"role": "user", "content": json.dumps(build_observation(email, order), default=str)},
    ]
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

    try:
        final: LLMResult | None = None
        for round_ in range(1, MAX_ROUNDS + 1):
            result = router.complete(
                TaskType.PLANNING, messages, max_tokens=PLANNER_MAX_TOKENS, tools=TOOL_SPECS,
                reasoning=True, run_id=run.id,
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
                                    reasoning=True, run_id=run.id)
            llm_step(MAX_ROUNDS + 1, "final", final)

        try:
            report = _parse_report(final.content)
        except ValidationError as exc:
            # One retry without thinking, so the budget goes to the answer.
            messages += [
                {"role": "assistant", "content": final.content or ""},
                {"role": "user", "content": prompt.FIX_JSON.format(error=str(exc)[:300])},
            ]
            retry = router.complete(TaskType.RISK_REASONING, messages, max_tokens=FINAL_MAX_TOKENS,
                                    reasoning=False, run_id=run.id)
            llm_step(run.rounds + 1, "final_retry", retry)
            try:
                report = _parse_report(retry.content)
            except ValidationError as retry_exc:
                report = RiskReport(summary="The agent did not return a valid risk report; review manually.")
                run.error = str(retry_exc)[:1000]

    except LLMError as exc:
        run.status = "failed"
        run.error = str(exc)[:1000]
        run.finished_at = datetime.now(UTC)
        session.commit()
        if isinstance(exc, SpendCapExceeded):
            raise
        return run

    _verify_evidence(report, evidence)
    _apply_safety_rules(report, evidence)
    run.result = report.model_dump(mode="json")
    run.status = "needs_review" if run.error else "completed"
    run.finished_at = datetime.now(UTC)
    session.commit()
    return run
