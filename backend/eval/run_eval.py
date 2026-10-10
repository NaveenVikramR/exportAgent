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
from app.services.drafting import generate_drafts
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
    info_checked: int = 0


@dataclass
class DraftResult:
    case_id: str
    kind: str
    words: int
    checked: int
    violations: list[dict]
    cost: Decimal


@dataclass
class AgentPass:
    label: str
    prefetch: bool
    results: list[AgentResult]
    usage: list
    drafts: list[DraftResult] = field(default_factory=list)

    def per_email(self, attribute: str) -> float | Decimal:
        values = [getattr(r, attribute) for r in self.results]
        return (sum(values, type(values[0])()) / len(values)) if values else 0


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
    agent_passes: list[AgentPass] | None = None,
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

    for agent_pass in agent_passes or []:
        if agent_pass is not agent_passes[-1]:
            continue
        lines += [
            "",
            "## Risk agent (Ultra)",
            "",
            "Runs on every email linked to an order. With pre-fetch, Python looks up the order, diffs it and "
            "checks feasibility (and proposes delivery options) before the loop; Ultra keeps the optional "
            "tools and the final judgement. The flag policy then moves anything without specific evidence "
            "to *Info checked* and corrects severities to the rubric.",
            "",
            "| Metric | " + " | ".join(p.label for p in agent_passes) + " |",
            "|---|" + "---|" * len(agent_passes),
            "| Emails assessed | " + " | ".join(str(len(p.results)) for p in agent_passes) + " |",
            "| Average Ultra calls per email | " + " | ".join(f"{p.per_email('ultra_calls'):.1f}" for p in agent_passes) + " |",
            "| Average Ultra cost per email | " + " | ".join(_usd(p.per_email("ultra_cost")) for p in agent_passes) + " |",
            "| Average tool rounds per email (cap 8) | " + " | ".join(f"{p.per_email('rounds'):.1f}" for p in agent_passes) + " |",
        ]
        for severity in ("high", "medium", "low"):
            lines.append(f"| {severity.capitalize()} flags | " + " | ".join(
                str(sum(1 for r in p.results for f in r.flags if f["severity"] == severity)) for p in agent_passes
            ) + " |")
        lines.append("| Info checked items | " + " | ".join(str(sum(r.info_checked for r in p.results)) for p in agent_passes) + " |")
        lines += [
            "",
            f"Per case ({agent_pass.label}):",
            "",
            "| Case | Status | Rounds | Ultra calls | Ultra cost | Tools called (round 0 = pre-fetched) | Flags | Info |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for a in agent_pass.results:
            flags = ", ".join(
                f"**{f['severity']}** {f['category']}" + (" (rule)" if f.get("source") == "rule" else "")
                for f in a.flags
            ) or "none"
            lines.append(
                f"| {a.case_id} | {a.status} | {a.rounds} | {a.ultra_calls} | {_usd(a.ultra_cost)} "
                f"| {', '.join(a.tools) or '-'} | {flags} | {a.info_checked} |"
            )

        if agent_pass.drafts:
            drafts = agent_pass.drafts
            violations = [v for d in drafts for v in d.violations]
            emails = {d.case_id for d in drafts}
            draft_cost = sum((d.cost for d in drafts), Decimal("0"))
            lines += [
                "",
                "## Drafts (Super) and fact check",
                "",
                "Every date, quantity and price in a draft must appear in the order data, the tool results or "
                "the buyer's email; anything else is a violation shown to the reviewer.",
                "",
                "| Metric | Result |",
                "|---|---|",
                f"| Drafts written | {len(drafts)} ({sum(d.kind == 'buyer_reply' for d in drafts)} replies, "
                f"{sum(d.kind == 'internal_note' for d in drafts)} internal notes) |",
                f"| Values checked | {sum(d.checked for d in drafts)} |",
                f"| Fact-check violations | {len(violations)} |",
                f"| Drafts with no violations | {_pct(sum(not d.violations for d in drafts), len(drafts))} |",
                f"| Average drafting cost per email | {_usd(draft_cost / len(emails))} |",
                "",
                "| Case | Draft | Words | Values checked | Violations |",
                "|---|---|---|---|---|",
            ]
            for d in drafts:
                found = "; ".join(f"{v['kind']}: {v['text']}" for v in d.violations) or "none"
                lines.append(f"| {d.case_id} | {d.kind} | {d.words} | {d.checked} | {found} |")

    usage = [("Scoring", row) for row in _usage_rows(first_call_id)] + [
        (p.label, row) for p in agent_passes or [] for row in p.usage
    ]
    total_cost = sum((Decimal(str(row[7])) for _, row in usage), Decimal("0"))
    lines += [
        "",
        "## Cost and latency (this run)",
        "",
        "Source `cache` means the response was reused from an earlier identical request at no cost. "
        "For real cost and latency, run with `LLM_CACHE_ENABLED=false`. With `--agent`, the agent's Ultra "
        "calls and Super's escalation and drafting calls are included per agent pass; Nano's analysis calls "
        "in the agent passes are not repeated here.",
        "",
        "| Pass | Model | Tier | Source | Calls | Input tokens | Output tokens | Avg latency | Cost (USD) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for label, (model, tier, source, calls, tokens_in, tokens_out, latency, cost) in usage:
        lines.append(
            f"| {label} | `{model}` | {tier} | {source} | {calls} | {tokens_in} | {tokens_out} | "
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


def run_agent_pass(cases: list[Case], *, prefetch: bool, drafts: bool, label: str) -> AgentPass:
    """Real order store, risk agent (and drafts) in a scratch database; caches shared with the main one."""
    scratch_dir = tempfile.mkdtemp(prefix="exportagent-eval-")
    engine = create_engine(f"sqlite:///{Path(scratch_dir, 'eval.db').as_posix()}")
    Base.metadata.create_all(engine)
    Scratch = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as main, Scratch() as scratch:
        for row in main.scalars(select(SearchCache)):
            scratch.merge(SearchCache(key=row.key, query=row.query, response=row.response))
        scratch.commit()

    router = LLMRouter(get_settings(), session_factory=Scratch, cache_session_factory=SessionLocal)
    result = AgentPass(label=label, prefetch=prefetch, results=[], usage=[])
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
            if email.order_id is not None:
                run = run_agent(session, email, router, prefetch=prefetch)
                calls = session.scalars(select(LLMCall).where(LLMCall.run_id == run.id)).all()
                ultra = [c for c in calls if c.tier == "ultra"]
                report = run.result or {}
                result.results.append(
                    AgentResult(
                        case_id=case.id,
                        status=run.status,
                        rounds=run.rounds,
                        ultra_calls=len(ultra),
                        ultra_cost=sum((c.cost_usd for c in ultra), Decimal("0")),
                        cost=sum((c.cost_usd for c in calls), Decimal("0")),
                        tools=[f"{s.name}" + (" (0)" if s.round == 0 else "") for s in run.steps if s.kind == "tool"],
                        flags=report.get("flags", []),
                        info_checked=len(report.get("info_checked", [])),
                    )
                )
                print(f"{case.id}: agent ({label}) {run.status}, {len(ultra)} Ultra calls")
            if drafts and email.classification is not None:
                for draft in generate_drafts(session, email, router):
                    call = session.get(LLMCall, draft.call_id) if draft.call_id else None
                    check = draft.fact_check or {}
                    result.drafts.append(DraftResult(
                        case_id=case.id, kind=draft.kind, words=len(draft.body.split()),
                        checked=check.get("checked", 0), violations=check.get("violations", []),
                        cost=call.cost_usd if call else Decimal("0"),
                    ))

        with SessionLocal() as main:
            for row in session.scalars(select(SearchCache)):
                main.merge(SearchCache(key=row.key, query=row.query, response=row.response))
            main.commit()
    result.usage = [row for row in _usage_rows(0, Scratch) if row[1] in ("ultra", "super")]
    engine.dispose()
    return result


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "report.md")
    parser.add_argument("--agent", action="store_true", help="also run the order store, risk agent and drafts")
    parser.add_argument("--compare-prefetch", action="store_true",
                        help="with --agent: run the agent without and with pre-fetch and compare")
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

    passes: list[AgentPass] | None = None
    if args.agent:
        passes = []
        if args.compare_prefetch:
            passes.append(run_agent_pass(cases, prefetch=False, drafts=False, label="Full loop (before)"))
        passes.append(run_agent_pass(cases, prefetch=True, drafts=True, label="Pre-fetch (after)"))
    results.sort(key=lambda r: r.case_id)
    report = build_report(results, failures, first_call_id, passes)
    args.out.write_text(report, encoding="utf-8")
    print(f"\n{report}\nWritten to {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
