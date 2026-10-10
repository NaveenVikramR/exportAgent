"""Buyer reply and internal note drafts, written by Super from facts assembled in Python.

Every draft is fact-checked and waits in the approval queue; nothing is sent.
"""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.prompts import drafting as prompt
from app.llm.router import LLMResult, LLMRouter
from app.llm.tasks import TaskType
from app.models import AgentRun, Draft, Email
from app.services.analysis import email_text
from app.services.fact_check import fact_check
from app.services.profiles import load_profile

DRAFT_MAX_TOKENS = 3000
_SCALARS = (
    "buyer", "po_number", "style", "currency", "unit_price", "total_quantity",
    "delivery_date", "incoterms", "port", "destination_country",
)
# Feasibility fields the reply may use; the list of other orders stays internal.
_PLAN_FIELDS = ("verdict", "reason", "delivery_date", "quantity", "shortfall_pcs", "fabric_ready")


class DraftingError(RuntimeError):
    """Drafting cannot start, e.g. the order has not been risk-assessed yet."""


def latest_run(session: Session, email: Email) -> AgentRun | None:
    return session.scalar(
        select(AgentRun)
        .where(AgentRun.email_id == email.id, AgentRun.status.in_(("completed", "needs_review")))
        .order_by(AgentRun.id.desc())
        .limit(1)
    )


def build_facts(session: Session, email: Email) -> dict[str, Any]:
    """Everything a draft may state, in one JSON object."""
    profile = load_profile(email.order.profile if email.order else get_settings().factory_profile)
    classification = email.classification or {}
    extraction = email.extraction or {}
    fields = extraction.get("fields") or {}
    facts: dict[str, Any] = {
        "factory": {"name": profile.factory, "contact_name": profile.contact_name, "contact_role": profile.contact_role},
        "buyer_email": {
            "from": email.sender,
            "subject": email.subject,
            "received": email.received_at.date().isoformat(),
            "requests": classification.get("intents", []),
            "summary": classification.get("summary"),
        },
        "missing_information": [
            flag["field"].replace("_", " ") for flag in extraction.get("review", []) if flag["reason"] == "missing"
        ],
    }

    order = email.order
    if order is not None and order.versions:
        current = order.versions[-1]
        facts["order"] = {name: current.data.get(name) for name in _SCALARS} | {
            "line_items": current.data.get("line_items", []), "version": current.version,
        }
        if len(order.versions) >= 2:
            previous = order.versions[-2]
            facts["previous_version"] = {name: previous.data.get(name) for name in _SCALARS} | {"version": previous.version}
        facts["changes"] = [
            {"field": c["field"], "old": c["old"], "new": c["new"], "detail": c["detail"]} for c in current.changes or []
        ]
    elif fields:
        facts["order"] = {name: (fields.get(name) or {}).get("value") for name in _SCALARS} | {
            "line_items": fields.get("line_items", []),
        }

    run = latest_run(session, email)
    if run is not None:
        report = run.result or {}
        facts["risk_flags"] = [
            {"severity": f["severity"], "category": f["category"], "reason": f["reason"]} for f in report.get("flags", [])
        ]
        for step in run.steps:
            output = step.output or {}
            if step.name == "check_delivery_feasibility" and "verdict" in output:
                plan = {key: output.get(key) for key in _PLAN_FIELDS}
                facts.setdefault("delivery_check", {})["current_plan" if output.get("is_current_plan") else "other_plan"] = plan
            elif step.name == "propose_delivery_options" and output.get("options_needed"):
                facts["delivery_options"] = {
                    "earliest_feasible_date_full_quantity": output.get("earliest_feasible_date_full_quantity"),
                    "partial_shipment": output.get("partial_shipment"),
                }
            elif step.name == "diff_po_versions" and output.get("contract_value"):
                facts["contract_value"] = output["contract_value"]
    return facts


def _write(router: LLMRouter, task: TaskType, system: str, user: str) -> LLMResult:
    result = router.complete(
        task, [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=DRAFT_MAX_TOKENS, temperature=0.3, reasoning=True,
    )
    if not (result.content or "").strip() or result.finish_reason == "length":
        # Thinking used the budget; ask again without it rather than store an empty draft.
        result = router.complete(
            task, [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=DRAFT_MAX_TOKENS, temperature=0.3, reasoning=False,
            detail="retry without thinking: empty or truncated draft",
        )
    return result


def generate_drafts(session: Session, email: Email, router: LLMRouter) -> list[Draft]:
    """A buyer reply, plus an internal note when the email concerns an order."""
    if email.classification is None:
        raise DraftingError("Analyse the email before drafting a reply.")
    if email.order_id is not None and latest_run(session, email) is None:
        raise DraftingError("Assess the order's risk before drafting, so the reply is grounded in it.")

    profile = load_profile(email.order.profile if email.order else get_settings().factory_profile)
    facts = build_facts(session, email)
    facts_json = json.dumps(facts, indent=1, default=str)
    source_text = email_text(email)
    user = prompt.user_message(facts_json, source_text)

    jobs = [("buyer_reply", TaskType.DRAFT_REPLY, prompt.reply_system(profile))]
    if email.order_id is not None:
        jobs.append(("internal_note", TaskType.DRAFT_INTERNAL_NOTE, prompt.note_system(profile)))

    for old in session.scalars(select(Draft).where(Draft.email_id == email.id, Draft.status == "pending")):
        old.status = "superseded"

    run = latest_run(session, email)
    drafts = []
    for kind, task, system in jobs:
        result = _write(router, task, system, user)
        body = (result.content or "").strip()
        draft = Draft(
            email_id=email.id,
            order_id=email.order_id,
            run_id=run.id if run else None,
            kind=kind,
            subject=f"Re: {email.subject}" if kind == "buyer_reply" else f"Internal: {email.subject}",
            body=body,
            fact_check=fact_check(body, facts, source_text) | {"facts": facts},
            call_id=result.call_id,
            status="pending",
        )
        session.add(draft)
        drafts.append(draft)
    session.commit()
    return drafts


def recheck(draft: Draft, session: Session) -> None:
    """Re-run the fact check on the reviewer's edited text against the same facts."""
    email = session.get(Email, draft.email_id)
    facts = (draft.fact_check or {}).get("facts") or build_facts(session, email)
    text = draft.edited_body if draft.edited_body is not None else draft.body
    draft.fact_check = fact_check(text, facts, email_text(email)) | {"facts": facts}


def approve(draft: Draft, reviewer: str) -> None:
    """Marks the draft sent. No real email leaves the system."""
    now = datetime.now(UTC)
    draft.status, draft.reviewed_by, draft.reviewed_at, draft.sent_at = "sent", reviewer, now, now


def reject(draft: Draft, reviewer: str, reason: str | None) -> None:
    draft.status, draft.reviewed_by, draft.reviewed_at, draft.reject_reason = "rejected", reviewer, datetime.now(UTC), reason
