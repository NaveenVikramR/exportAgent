"""Builds eval/REPORT.md from the passes in eval/runs/ (see eval/run_eval.py).

Every metric is computed per pass; repeated passes are shown as mean (min-max).
Hand-written sections (failure analysis, change log, labels to verify) come from
eval/report_notes.md and are inserted as they are.

Usage (from backend/):  python -m eval.report
"""

import json
import sys
from collections import defaultdict
from decimal import Decimal
from statistics import mean
from typing import Any

from eval.dataset import EVAL_DIR

RUNS_DIR = EVAL_DIR / "runs"
NOTES = EVAL_DIR / "report_notes.md"
OUT = EVAL_DIR / "REPORT.md"
TIERS = ("nano", "super", "ultra")


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def metrics(run: dict[str, Any]) -> dict[str, float | None]:
    records = run["records"]
    done = [r for r in records if "error" not in r]
    scores = [r["score"] for r in done]
    before = [r["score_before_escalation"] for r in done]

    def field_acc(rows):
        values = [ok for s in rows for ok in s["fields"].values()]
        return _ratio(sum(values), len(values))

    def items_acc(rows):
        return _ratio(sum(s["line_items_correct"] for s in rows), sum(s["line_items_total"] for s in rows))

    changes = [r["changes"] for r in done]
    tp = sum(len(set(r["predicted_high"]) & set(r["expected_high"])) for r in done)
    fp = sum(len(set(r["predicted_high"]) - set(r["expected_high"])) for r in done)
    fn = sum(len(set(r["expected_high"]) - set(r["predicted_high"])) for r in done)
    drafts = [d for r in done for d in r.get("drafts", [])]
    extracted = [r for r in done if r["has_extraction"]]
    escalated = [r for r in extracted if r["escalations"]]
    escalations = [e for r in extracted for e in r["escalations"]]
    assessed = [r for r in done if "agent" in r]
    review_expected = sum(len(s["review_expected"]) for s in scores)
    review_hits = sum(len(set(s["review_expected"]) & set(s["review_flagged"])) for s in scores)
    review_flagged = sum(len(s["review_flagged"]) for s in scores)

    def tier_total(tier: str, key: str) -> float:
        return sum(float(r["usage"].get(tier, {}).get(key, 0)) for r in records)

    n = len(records)
    out = {
        "emails": n,
        "errors": n - len(done),
        "category": _ratio(sum(s["category_ok"] for s in scores), len(scores)),
        "intents": _ratio(sum(s["intents_ok"] for s in scores), len(scores)),
        "has_po_data": _ratio(sum(s["has_po_data_ok"] for s in scores), len(scores)),
        "fields": field_acc(scores),
        "fields_before": field_acc(before),
        "line_items": items_acc(scores),
        "line_items_before": items_acc(before),
        "review_recall": _ratio(review_hits, review_expected),
        "review_precision": _ratio(review_hits, review_flagged),
        "change_recall": _ratio(sum(c["correct"] for c in changes), sum(c["expected"] for c in changes)),
        "change_precision": _ratio(sum(c["correct"] for c in changes), sum(c["predicted"] for c in changes)),
        "high_precision": _ratio(tp, tp + fp),
        "high_recall": _ratio(tp, tp + fn),
        "drafts": len(drafts),
        "draft_values_checked": sum(d["checked"] for d in drafts),
        "draft_violations": sum(len(d["violations"]) for d in drafts),
        "drafts_clean": _ratio(sum(not d["violations"] for d in drafts), len(drafts)),
        "escalation_rate": _ratio(len(escalated), len(extracted)),
        "nano_alone": _ratio(len(extracted) - len(escalated), len(extracted)),
        "fields_escalated": len(escalations),
        "escalations_resolved": _ratio(sum(e["outcome"] == "resolved" for e in escalations), len(escalations)),
        "ultra_calls_per_assessed": _ratio(sum(r["usage"].get("ultra", {}).get("calls", 0) for r in assessed), len(assessed)),
        "assessed": len(assessed),
        "cost_per_email": _ratio(sum(tier_total(t, "cost") for t in TIERS), n),
        "seconds_per_email": mean(r["seconds"] for r in records) if records else None,
        "total_cost": sum(tier_total(t, "cost") for t in TIERS),
    }
    for tier in TIERS:
        out[f"{tier}_cost_per_email"] = _ratio(tier_total(tier, "cost"), n)
        out[f"{tier}_calls_per_email"] = _ratio(tier_total(tier, "calls"), n)
        out[f"{tier}_seconds_per_email"] = _ratio(tier_total(tier, "latency_ms") / 1000, n)
    out["field_gain"] = out["fields"] - out["fields_before"] if out["fields"] is not None and out["fields_before"] is not None else None
    out["line_item_gain"] = (out["line_items"] - out["line_items_before"]
                             if out["line_items"] is not None and out["line_items_before"] is not None else None)
    return out


def _load() -> dict[tuple[str, str], list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for path in sorted(RUNS_DIR.glob("*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        if run.get("llm_mode") != "live" or run.get("cache"):
            continue
        groups[(run["split"], run["variant"])].append(run)
    return groups


def _fmt(values: list[float | None], kind: str) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "n/a"

    def one(v: float) -> str:
        if kind == "pct":
            return f"{v * 100:.1f}%"
        if kind == "pp":
            return f"{v * 100:+.1f} pp"
        if kind == "usd":
            return f"${v:.4f}"
        if kind == "s":
            return f"{v:.1f} s"
        if kind == "f1":
            return f"{v:.1f}"
        return f"{v:.0f}"

    if len(values) == 1:
        return one(values[0])
    return f"{one(mean(values))} ({one(min(values))}–{one(max(values))})"


MAIN_ROWS = [
    ("Classification: main category", "category", "pct"),
    ("Classification: all intents (exact set)", "intents", "pct"),
    ("Classification: has PO data", "has_po_data", "pct"),
    ("Field extraction accuracy (after escalation)", "fields", "pct"),
    ("Line-item accuracy (colour, quantity, sizes)", "line_items", "pct"),
    ("Human-review flags: recall", "review_recall", "pct"),
    ("Human-review flags: precision", "review_precision", "pct"),
    ("Change detection: recall", "change_recall", "pct"),
    ("Change detection: precision", "change_precision", "pct"),
    ("High-risk flags: precision", "high_precision", "pct"),
    ("High-risk flags: recall", "high_recall", "pct"),
    ("Drafts written", "drafts", "n"),
    ("Draft values fact-checked", "draft_values_checked", "n"),
    ("Draft fact-check violations", "draft_violations", "f1"),
    ("Drafts with no violations", "drafts_clean", "pct"),
    ("Escalation rate (emails with an escalated field)", "escalation_rate", "pct"),
    ("Emails handled by Nano alone", "nano_alone", "pct"),
    ("Escalations resolved by Super", "escalations_resolved", "pct"),
    ("Escalation gain: field accuracy", "field_gain", "pp"),
    ("Escalation gain: line-item accuracy", "line_item_gain", "pp"),
    ("Ultra calls per assessed email", "ultra_calls_per_assessed", "f1"),
    ("Cost per email (all models)", "cost_per_email", "usd"),
    ("Latency per email (wall clock, end to end)", "seconds_per_email", "s"),
    ("Emails that failed to process", "errors", "n"),
]


def build() -> str:
    groups = _load()
    per = {key: [metrics(run) for run in runs] for key, runs in groups.items()}

    def col(split: str, variant: str, key: str, kind: str) -> str:
        return _fmt([m[key] for m in per.get((split, variant), [])], kind)

    dev_runs, test_runs = len(per.get(("dev", "routed"), [])), len(per.get(("test", "routed"), []))
    total_spend = sum(m["total_cost"] for runs in per.values() for m in runs)
    lines = [
        "# ExportAgent evaluation report",
        "",
        f"Routed setup run {dev_runs}× on DEV (10 cases) and {test_runs}× on TEST (30 held-out cases), "
        "end to end with the response cache off: classification and extraction, escalation, the order store "
        "and change detection, the risk agent, and drafts with the fact check. Values are mean (min–max) "
        "across runs. Baselines ran once on TEST.",
        "",
        f"Model spend in these runs: **${total_spend:.2f}**.",
        "",
        "## Results: routed setup",
        "",
        "| Metric | DEV | TEST |",
        "|---|---|---|",
    ]
    for label, key, kind in MAIN_ROWS:
        lines.append(f"| {label} | {col('dev', 'routed', key, kind)} | {col('test', 'routed', key, kind)} |")

    lines += [
        "",
        "## Cost and latency by model (routed, per email)",
        "",
        "Per email over all emails in the split (emails without an order make no Ultra call). Latency here is the sum "
        "of model-call time; the table above is wall clock including search and database work.",
        "",
        "| Model | DEV cost | TEST cost | DEV calls | TEST calls | DEV model time | TEST model time |",
        "|---|---|---|---|---|---|---|",
    ]
    for tier in TIERS:
        lines.append(
            f"| {tier.capitalize()} | {col('dev', 'routed', f'{tier}_cost_per_email', 'usd')} "
            f"| {col('test', 'routed', f'{tier}_cost_per_email', 'usd')} "
            f"| {col('dev', 'routed', f'{tier}_calls_per_email', 'f1')} "
            f"| {col('test', 'routed', f'{tier}_calls_per_email', 'f1')} "
            f"| {col('dev', 'routed', f'{tier}_seconds_per_email', 's')} "
            f"| {col('test', 'routed', f'{tier}_seconds_per_email', 's')} |"
        )

    baseline_rows = [
        ("Classification: main category", "category", "pct"),
        ("Field extraction accuracy", "fields", "pct"),
        ("Line-item accuracy", "line_items", "pct"),
        ("Change detection: recall", "change_recall", "pct"),
        ("Change detection: precision", "change_precision", "pct"),
        ("High-risk flags: precision", "high_precision", "pct"),
        ("High-risk flags: recall", "high_recall", "pct"),
        ("Ultra calls per assessed email", "ultra_calls_per_assessed", "f1"),
        ("Cost per email (extraction + risk)", "cost_per_email", "usd"),
        ("Latency per email", "seconds_per_email", "s"),
        ("Emails that failed to process", "errors", "n"),
    ]
    lines += [
        "",
        "## Baselines on TEST (extraction + risk, no drafts)",
        "",
        "Nano-only runs every task on Nano with no escalation; Ultra-for-everything runs every task on Ultra. "
        "The routed column excludes drafting cost so the three are comparable.",
        "",
        "| Metric | Nano only | Routed (ours) | Ultra for everything |",
        "|---|---|---|---|",
    ]
    for label, key, kind in baseline_rows:
        if key == "cost_per_email":
            routed = _fmt([m["cost_per_email"] - (m["super_cost_per_email"] or 0) + _escalation_cost(run)
                           for m, run in zip(per.get(("test", "routed"), []), groups.get(("test", "routed"), []))], kind)
        else:
            routed = col("test", "routed", key, kind)
        lines.append(f"| {label} | {col('test', 'nano_only', key, kind)} | {routed} | {col('test', 'ultra_all', key, kind)} |")

    lines += _per_case(groups.get(("test", "routed"), []))
    if NOTES.exists():
        lines += ["", NOTES.read_text(encoding="utf-8").strip()]
    return "\n".join(lines) + "\n"


def _escalation_cost(run: dict) -> float:
    """Super spend on escalations (kept), as opposed to drafting (excluded from the baseline comparison)."""
    return sum(float(e["cost_usd"]) for r in run["records"] for e in r.get("escalations", [])) / len(run["records"])


def _per_case(runs: list[dict]) -> list[str]:
    if not runs:
        return []
    lines = [
        "",
        "## TEST per case (routed)",
        "",
        "Field and line-item accuracy averaged over the runs; high-risk groups per run (expected → predicted).",
        "",
        "| Case | Fields | Line items | Changes found | Expected high | Predicted high per run | Draft violations |",
        "|---|---|---|---|---|---|---|",
    ]
    by_case: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        for record in run["records"]:
            by_case[record["case_id"]].append(record)
    for case_id in sorted(by_case):
        records = [r for r in by_case[case_id] if "error" not in r]
        if not records:
            lines.append(f"| {case_id} | error | | | | | |")
            continue
        fields = [ok for r in records for ok in r["score"]["fields"].values()]
        items = sum(r["score"]["line_items_correct"] for r in records), sum(r["score"]["line_items_total"] for r in records)
        changes = sum(r["changes"]["correct"] for r in records), sum(r["changes"]["expected"] for r in records)
        violations = sum(len(d["violations"]) for r in records for d in r.get("drafts", []))
        lines.append(
            f"| {case_id} | {_fmt([_ratio(sum(fields), len(fields))], 'pct') if fields else '–'} "
            f"| {_fmt([_ratio(*items)], 'pct') if items[1] else '–'} "
            f"| {f'{changes[0]}/{changes[1]}' if changes[1] else '–'} "
            f"| {', '.join(records[0]['expected_high']) or '–'} "
            f"| {' / '.join(', '.join(r['predicted_high']) or '–' for r in records)} | {violations} |"
        )
    return lines


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    report = build()
    OUT.write_text(report, encoding="utf-8")
    print(report)
    print(f"Written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
