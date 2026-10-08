"""Runs the pipeline on every eval case and scores it against the labels.

Cases run in the order the emails arrived, against an in-memory order store, so
a revised PO is compared with the version an earlier case created.

With --agent, the cases also go through the real order store and the risk
agent in a scratch database (sharing the main response and search caches), and
the report adds Ultra usage and the risk flags per case.

Usage (from backend/):  python -m eval.run_eval [--agent] [--out eval/report.md]
"""

import argparse
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.agent.loop import run_agent
from app.agent.tools.diff_po_versions import plan_versions, snapshot_from_extraction
from app.config import get_settings
from app.db import Base, SessionLocal
from app.llm.router import LLMError, LLMRouter, get_router
from app.models import AgentRun, Email, EmailAttachment, LLMCall, SearchCache
from app.schemas.extraction import SCALAR_FIELDS, Escalation
from app.services.analysis import Analysis, analyse_email, analyse_text, render_email_text
from app.services.orders import normalise_po_number
from eval.dataset import EVAL_DIR, Case, load_cases, load_expected
from eval.scoring import CaseScore, ChangeScore, score_case, score_changes

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}


def _pct(correct: int, total: int) -> str:
    return f"{correct}/{total} ({correct / total:.0%})" if total else "n/a"


def _usd(value: Decimal) -> str:
    return f"${value:.4f}"


def _max_call_id() -> int:
    with SessionLocal() as session:
        return session.scalar(select(func.coalesce(func.max(LLMCall.id), 0)))


def _text(case: Case) -> str:
    return render_email_text(
        sender=case.sender,
        subject=case.subject,
        received_at=case.received_at.isoformat(),
        body=case.body,
        attachments=[(a["filename"], a["text"]) for a in case.attachments],
    )


def predict_changes(store: dict[str, dict], analysis: Analysis) -> list:
    """The same versioning the order store applies, kept in memory."""
    if not analysis.extraction or not analysis.extraction.fields.po_number.value:
        return []
    key = normalise_po_number(analysis.extraction.fields.po_number.value)
    planned = plan_versions(store.get(key), snapshot_from_extraction(analysis.extraction.fields), analysis.stated_changes)
    if planned:
        store[key] = planned[-1].data
    return [change for version in planned for change in version.changes]


@dataclass
class CaseResult:
    case_id: str
    after: CaseScore
    before: CaseScore
    changes: ChangeScore
    has_extraction: bool
    escalations: list[Escalation] = field(default_factory=list)


@dataclass
class AgentResult:
    case_id: str
    status: str
    rounds: int
    ultra_calls: int
    ultra_cost: Decimal
    cost: Decimal
    tools: list[str]
    flags: list[dict]


def _field_accuracy(scores: list[CaseScore]) -> tuple[dict[str, list[bool]], list[bool]]:
    per_field: dict[str, list[bool]] = defaultdict(list)
    for score in scores:
        for name, ok in score.fields.items():
            per_field[name].append(ok)
    return per_field, [ok for results in per_field.values() for ok in results]


def _usage_rows(first_call_id: int, session_factory=SessionLocal):
    with session_factory() as session:
        return session.execute(
            select(
                LLMCall.model, LLMCall.tier, LLMCall.source, func.count(LLMCall.id),
                func.sum(LLMCall.input_tokens), func.sum(LLMCall.output_tokens),
                func.avg(LLMCall.latency_ms), func.sum(LLMCall.cost_usd),
            )
            .where(LLMCall.id > first_call_id)
            .group_by(LLMCall.model, LLMCall.tier, LLMCall.source)
        ).all()


def build_report(
    results: list[CaseResult],
    failures: dict[str, str],
    first_call_id: int,
    agent_results: list[AgentResult] | None = None,
    agent_usage: list | None = None,
) -> str:
    settings = get_settings()
    after = [r.after for r in results]
    before = [r.before for r in results]
    n = len(results)
    lines = [
        "# ExportAgent evaluation report",
        "",
        f"- Generated: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        f"- Cases scored: {n} (failed to run: {len(failures)})",
        f"- LLM mode: `{settings.llm_mode}`",
    ]
    if settings.llm_mode == "mock":
        lines += [
            "",
            "> **Mock mode.** These numbers measure the rule-based stand-ins in `app/llm/mock.py` and "
            "`app/llm/mock_agent.py`, not Nemotron. They show that the pipeline and the scoring run end "
            "to end; they say nothing about model quality.",
        ]

    lines += ["", "## Classification", "", "| Metric | Result |", "|---|---|"]
    lines.append(f"| Category | {_pct(sum(s.category_ok for s in after), n)} |")
    lines.append(f"| All intents (exact set) | {_pct(sum(s.intents_ok for s in after), n)} |")
    lines.append(f"| Has PO data | {_pct(sum(s.has_po_data_ok for s in after), n)} |")

    per_field_before, all_before = _field_accuracy(before)
    per_field_after, all_after = _field_accuracy(after)
    lines += [
        "",
        "## Field extraction",
        "",
        "Nano extracts every field; fields that fail a Python check are re-extracted by Super (see Escalation).",
        "",
        "| Field | Nano only | After escalation |",
        "|---|---|---|",
    ]
    for name in SCALAR_FIELDS:
        lines.append(
            f"| {name} | {_pct(sum(per_field_before[name]), len(per_field_before[name]))} "
            f"| {_pct(sum(per_field_after[name]), len(per_field_after[name]))} |"
        )
    lines.append(f"| **All fields** | **{_pct(sum(all_before), len(all_before))}** | **{_pct(sum(all_after), len(all_after))}** |")
    lines.append(
        f"| Line items (colour, quantity, sizes) "
        f"| {_pct(sum(s.line_items_correct for s in before), sum(s.line_items_total for s in before))} "
        f"| {_pct(sum(s.line_items_correct for s in after), sum(s.line_items_total for s in after))} |"
    )

    extracted = [r for r in results if r.has_extraction]
    escalated = [r for r in extracted if r.escalations]
    all_escalations = [e for r in extracted for e in r.escalations]
    resolved = [e for e in all_escalations if e.outcome == "resolved"]
    escalation_cost = sum((e.cost_usd for e in all_escalations), Decimal("0"))
    lines += [
        "",
        "## Escalation (Nano → Super)",
        "",
        "Triggers: size breakdown does not add up, a size table was present but not extracted, "
        "or the quoted source text is missing or does not state the value. Only the failing field "
        "is re-extracted, and Super's value is kept only if the same check then passes.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Emails handled by Nano alone | {_pct(len(extracted) - len(escalated), len(extracted))} |",
        f"| Escalation rate (emails with at least one escalated field) | {_pct(len(escalated), len(extracted))} |",
        f"| Fields escalated | {len(all_escalations)} |",
        f"| Resolved by Super (check passed, value kept) | {_pct(len(resolved), len(all_escalations))} |",
        f"| Escalation cost | {_usd(escalation_cost)} |",
    ]
    if all_escalations:
        lines += ["", "| Case | Field | Reason | Model | Outcome | Cost |", "|---|---|---|---|---|---|"]
        for r in escalated:
            for e in r.escalations:
                lines.append(f"| {r.case_id} | {e.field} | {e.reason} | `{e.model}` | {e.outcome} | {_usd(e.cost_usd)} |")

    expected = sum(len(s.review_expected) for s in after)
    flagged = sum(len(s.review_flagged) for s in after)
    hits = sum(len(s.review_expected & s.review_flagged) for s in after)
    lines += ["", "## Human-review flags", "", "| Metric | Result |", "|---|---|"]
    lines.append(f"| Recall (fields that needed review and were flagged) | {_pct(hits, expected)} |")
    lines.append(f"| Precision (flagged fields that needed review) | {_pct(hits, flagged)} |")

    change_scores = [r.changes for r in results]
    lines += [
        "",
        "## Change detection",
        "",
        "A change counts as correct when its field and both old and new values match the label.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Recall (labelled changes found) | {_pct(sum(s.correct for s in change_scores), sum(s.expected for s in change_scores))} |",
        f"| Precision (reported changes that are correct) | {_pct(sum(s.correct for s in change_scores), sum(s.predicted for s in change_scores))} |",
    ]
    for s in change_scores:
        if s.missed or s.unexpected:
            lines.append(f"| {s.case_id} | missed {s.missed or '-'}, unexpected {s.unexpected or '-'} |")

    if agent_results is not None:
        assessed = len(agent_results)
        ultra_calls = sum(a.ultra_calls for a in agent_results)
        ultra_cost = sum((a.ultra_cost for a in agent_results), Decimal("0"))
        lines += [
            "",
            "## Risk agent (Ultra)",
            "",
            "Runs on every email linked to an order. Ultra plans and writes the report; tools do the maths.",
            "",
            "| Metric | Result |",
            "|---|---|",
            f"| Emails assessed | {assessed} |",
            f"| Average Ultra calls per email | {ultra_calls / assessed:.1f} |" if assessed else "| Average Ultra calls per email | n/a |",
            f"| Average Ultra cost per email | {_usd(ultra_cost / assessed)} |" if assessed else "| Average Ultra cost per email | n/a |",
            f"| Average tool rounds per email (cap 8) | {sum(a.rounds for a in agent_results) / assessed:.1f} |" if assessed else "| Average tool rounds | n/a |",
            f"| Total agent cost | {_usd(sum((a.cost for a in agent_results), Decimal('0')))} |",
            "",
            "| Case | Status | Rounds | Ultra calls | Ultra cost | Tools called | Flags |",
            "|---|---|---|---|---|---|---|",
        ]
        for a in agent_results:
            flags = ", ".join(
                f"**{f['severity']}** {f['category']}" + ("" if f.get("verified") else " (unverified)")
                for f in a.flags
            ) or "none"
            lines.append(
                f"| {a.case_id} | {a.status} | {a.rounds} | {a.ultra_calls} | {_usd(a.ultra_cost)} "
                f"| {', '.join(a.tools) or '-'} | {flags} |"
            )

    usage = list(_usage_rows(first_call_id)) + list(agent_usage or [])
    total_cost = sum((Decimal(str(row[7])) for row in usage), Decimal("0"))
    lines += [
        "",
        "## Cost and latency (this run)",
        "",
        "Source `cache` means the response was reused from an earlier identical request at no cost. "
        "For real cost and latency, run with `LLM_CACHE_ENABLED=false`. With `--agent`, the risk agent's "
        "Ultra calls are included.",
        "",
        "| Model | Tier | Source | Calls | Input tokens | Output tokens | Avg latency | Cost (USD) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, tier, source, calls, tokens_in, tokens_out, latency, cost in usage:
        lines.append(
            f"| `{model}` | {tier} | {source} | {calls} | {tokens_in} | {tokens_out} | "
            f"{round(latency)} ms | {Decimal(str(cost)):.6f} |"
        )
    if n:
        lines += ["", f"Average cost per case: ${total_cost / n:.6f}"]

    lines += ["", "## Per case", "", "| Case | Category | Intents | Fields | Line items | Review flags (expected / flagged) |", "|---|---|---|---|---|---|"]
    for s in after:
        lines.append(
            f"| {s.case_id} | {'ok' if s.category_ok else 'wrong'} | {'ok' if s.intents_ok else 'wrong'} | "
            f"{_pct(sum(s.fields.values()), len(s.fields))} | {_pct(s.line_items_correct, s.line_items_total)} | "
            f"{sorted(s.review_expected) or '-'} / {sorted(s.review_flagged) or '-'} |"
        )
    if failures:
        lines += ["", "## Failed to run", ""]
        lines += [f"- {case_id}: {error}" for case_id, error in failures.items()]
    return "\n".join(lines) + "\n"


def run_agent_pass(cases: list[Case]) -> tuple[list[AgentResult], list]:
    """Real order store + risk agent in a scratch database; caches shared with the main one."""
    scratch_dir = tempfile.mkdtemp(prefix="exportagent-eval-")
    engine = create_engine(f"sqlite:///{Path(scratch_dir, 'eval.db').as_posix()}")
    Base.metadata.create_all(engine)
    Scratch = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as main, Scratch() as scratch:
        for row in main.scalars(select(SearchCache)):
            scratch.merge(SearchCache(key=row.key, query=row.query, response=row.response))
        scratch.commit()

    router = LLMRouter(get_settings(), session_factory=Scratch, cache_session_factory=SessionLocal)
    results: list[AgentResult] = []
    with Scratch() as session:
        for case in cases:
            email = Email(
                external_id=case.id, sender=case.sender, subject=case.subject, body=case.body,
                received_at=datetime.combine(case.received_at, time(9, 0), tzinfo=UTC), source="eval",
                attachments=[EmailAttachment(filename=a["filename"], content_type=a["content_type"],
                                             text_content=a["text"]) for a in case.attachments],
            )
            session.add(email)
            session.commit()
            analyse_email(session, email, router)
            if email.order_id is None:
                continue
            run = run_agent(session, email, router)
            calls = session.scalars(select(LLMCall).where(LLMCall.run_id == run.id)).all()
            ultra = [c for c in calls if c.tier == "ultra"]
            results.append(
                AgentResult(
                    case_id=case.id,
                    status=run.status,
                    rounds=run.rounds,
                    ultra_calls=len(ultra),
                    ultra_cost=sum((c.cost_usd for c in ultra), Decimal("0")),
                    cost=sum((c.cost_usd for c in calls), Decimal("0")),
                    tools=[s.name for s in run.steps if s.kind == "tool"],
                    flags=(run.result or {}).get("flags", []),
                )
            )
            print(f"{case.id}: agent {run.status}, {len(ultra)} Ultra calls")

        with SessionLocal() as main:
            for row in session.scalars(select(SearchCache)):
                main.merge(SearchCache(key=row.key, query=row.query, response=row.response))
            main.commit()
    agent_usage = [
        row for row in _usage_rows(0, Scratch) if row[1] == "ultra"
    ]
    engine.dispose()
    return results, agent_usage


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "report.md")
    parser.add_argument("--agent", action="store_true", help="also run the order store and risk agent")
    args = parser.parse_args()

    cases = sorted(load_cases(), key=lambda case: (case.received_at, case.id))
    router = get_router()
    first_call_id = _max_call_id()
    results: list[CaseResult] = []
    store: dict[str, dict] = {}
    failures: dict[str, str] = {}
    for case in cases:
        try:
            analysis = analyse_text(router, _text(case))
        except LLMError as exc:
            failures[case.id] = str(exc)
            print(f"{case.id}: FAILED {exc}")
            continue
        expected = load_expected(case.id)
        nano_only = replace(analysis, extraction=analysis.extraction_before_escalation)
        results.append(
            CaseResult(
                case_id=case.id,
                after=score_case(case.id, expected, analysis),
                before=score_case(case.id, expected, nano_only),
                changes=score_changes(case.id, expected.get("expected_changes") or [], predict_changes(store, analysis)),
                has_extraction=analysis.extraction is not None,
                escalations=analysis.extraction.escalations if analysis.extraction else [],
            )
        )
        print(f"{case.id}: done")

    agent_results, agent_usage = run_agent_pass(cases) if args.agent else (None, None)
    results.sort(key=lambda r: r.case_id)
    report = build_report(results, failures, first_call_id, agent_results, agent_usage)
    args.out.write_text(report, encoding="utf-8")
    print(f"\n{report}\nWritten to {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
