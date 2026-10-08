"""Runs classification, extraction and change detection on every eval case and scores them.

Cases run in file order, against an in-memory order store, so a revised PO is
compared with the version an earlier case created.

Usage (from backend/):  python -m eval.run_eval [--out eval/report.md]
"""

import argparse
import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.llm.router import LLMError, get_router
from app.models import LLMCall
from app.schemas.extraction import SCALAR_FIELDS
from app.agent.tools.diff_po_versions import plan_versions, snapshot_from_extraction
from app.services.analysis import Analysis, analyse_text, render_email_text
from app.services.orders import normalise_po_number
from eval.dataset import EVAL_DIR, load_cases, load_expected
from eval.scoring import CaseScore, ChangeScore, score_case, score_changes


def _pct(correct: int, total: int) -> str:
    return f"{correct}/{total} ({correct / total:.0%})" if total else "n/a"


def _max_call_id() -> int:
    with SessionLocal() as session:
        return session.scalar(select(func.coalesce(func.max(LLMCall.id), 0)))


def predict_changes(store: dict[str, dict], analysis: Analysis) -> list:
    """The same versioning the order store applies, kept in memory."""
    if not analysis.extraction or not analysis.extraction.fields.po_number.value:
        return []
    key = normalise_po_number(analysis.extraction.fields.po_number.value)
    planned = plan_versions(store.get(key), snapshot_from_extraction(analysis.extraction.fields), analysis.stated_changes)
    if planned:
        store[key] = planned[-1].data
    return [change for version in planned for change in version.changes]


def build_report(
    scores: list[CaseScore],
    change_scores: list[ChangeScore],
    failures: dict[str, str],
    first_call_id: int,
) -> str:
    settings = get_settings()
    n = len(scores)
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
            "> **Mock mode.** These numbers measure the rule-based stand-in in `app/llm/mock.py`, "
            "not a Nemotron model. They show that the pipeline and the scoring run end to end; "
            "they say nothing about model quality.",
        ]

    lines += ["", "## Classification", "", "| Metric | Result |", "|---|---|"]
    lines.append(f"| Category | {_pct(sum(s.category_ok for s in scores), n)} |")
    lines.append(f"| All intents (exact set) | {_pct(sum(s.intents_ok for s in scores), n)} |")
    lines.append(f"| Has PO data | {_pct(sum(s.has_po_data_ok for s in scores), n)} |")

    per_field: dict[str, list[bool]] = defaultdict(list)
    for score in scores:
        for name, ok in score.fields.items():
            per_field[name].append(ok)
    all_fields = [ok for results in per_field.values() for ok in results]
    lines += ["", "## Field extraction", "", "| Field | Correct |", "|---|---|"]
    for name in SCALAR_FIELDS:
        lines.append(f"| {name} | {_pct(sum(per_field[name]), len(per_field[name]))} |")
    lines.append(f"| **All fields** | **{_pct(sum(all_fields), len(all_fields))}** |")
    items_total = sum(s.line_items_total for s in scores)
    lines.append(f"| Line items (colour, quantity, sizes) | {_pct(sum(s.line_items_correct for s in scores), items_total)} |")

    expected = sum(len(s.review_expected) for s in scores)
    flagged = sum(len(s.review_flagged) for s in scores)
    hits = sum(len(s.review_expected & s.review_flagged) for s in scores)
    lines += ["", "## Human-review flags", "", "| Metric | Result |", "|---|---|"]
    lines.append(f"| Recall (fields that needed review and were flagged) | {_pct(hits, expected)} |")
    lines.append(f"| Precision (flagged fields that needed review) | {_pct(hits, flagged)} |")

    expected_changes = sum(s.expected for s in change_scores)
    predicted_changes = sum(s.predicted for s in change_scores)
    correct_changes = sum(s.correct for s in change_scores)
    lines += [
        "",
        "## Change detection",
        "",
        "A change counts as correct when its field and both old and new values match the label.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Recall (labelled changes found) | {_pct(correct_changes, expected_changes)} |",
        f"| Precision (reported changes that are correct) | {_pct(correct_changes, predicted_changes)} |",
    ]
    for s in change_scores:
        if s.missed or s.unexpected:
            lines.append(f"| {s.case_id} | missed {s.missed or '-'}, unexpected {s.unexpected or '-'} |")

    with SessionLocal() as session:
        usage = session.execute(
            select(
                LLMCall.model,
                LLMCall.tier,
                LLMCall.source,
                func.count(LLMCall.id),
                func.sum(LLMCall.input_tokens),
                func.sum(LLMCall.output_tokens),
                func.avg(LLMCall.latency_ms),
                func.sum(LLMCall.cost_usd),
            )
            .where(LLMCall.id > first_call_id)
            .group_by(LLMCall.model, LLMCall.tier, LLMCall.source)
        ).all()
    total_cost = sum((Decimal(str(row[7])) for row in usage), Decimal("0"))
    lines += [
        "",
        "## Cost and latency",
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
    for s in scores:
        lines.append(
            f"| {s.case_id} | {'ok' if s.category_ok else 'wrong'} | {'ok' if s.intents_ok else 'wrong'} | "
            f"{_pct(sum(s.fields.values()), len(s.fields))} | {_pct(s.line_items_correct, s.line_items_total)} | "
            f"{sorted(s.review_expected) or '-'} / {sorted(s.review_flagged) or '-'} |"
        )
    if failures:
        lines += ["", "## Failed to run", ""]
        lines += [f"- {case_id}: {error}" for case_id, error in failures.items()]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "report.md")
    args = parser.parse_args()

    router = get_router()
    first_call_id = _max_call_id()
    scores: list[CaseScore] = []
    change_scores: list[ChangeScore] = []
    store: dict[str, dict] = {}
    failures: dict[str, str] = {}
    for case in load_cases():
        text = render_email_text(
            sender=case.sender,
            subject=case.subject,
            received_at=case.received_at.isoformat(),
            body=case.body,
            attachments=[(a["filename"], a["text"]) for a in case.attachments],
        )
        try:
            analysis = analyse_text(router, text)
        except LLMError as exc:
            failures[case.id] = str(exc)
            print(f"{case.id}: FAILED {exc}")
            continue
        expected = load_expected(case.id)
        scores.append(score_case(case.id, expected, analysis))
        change_scores.append(
            score_changes(case.id, expected.get("expected_changes") or [], predict_changes(store, analysis))
        )
        print(f"{case.id}: done")

    report = build_report(scores, change_scores, failures, first_call_id)
    args.out.write_text(report, encoding="utf-8")
    print(f"\n{report}\nWritten to {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
