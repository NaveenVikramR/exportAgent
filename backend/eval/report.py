"""Builds eval/REPORT.md from the passes in eval/runs/ (see eval/run_eval.py).

Every metric is computed per pass; repeated passes are shown as mean (min-max).
Passes from Milestone 7 are kept in eval/runs/m7/ and shown as the "before" column.
Hand-written sections (change log, failure analysis, caveats) come from
eval/report_notes.md and are inserted as they are.

Usage (from backend/):  python -m eval.report
"""

import json
import sys
from collections import defaultdict
from statistics import mean
from typing import Any

from eval.dataset import EVAL_DIR

RUNS_DIR = EVAL_DIR / "runs"
NOTES = EVAL_DIR / "report_notes.md"
OUT = EVAL_DIR / "REPORT.md"
TIERS = ("nano", "super", "ultra")
STAGES = ("extraction", "risk", "drafting")


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
    matches = [r["match"] for r in done if r.get("match")]
    routed_runs = [r["agent"]["routing"] for r in done if r.get("agent", {}).get("routing")]
    revisions = [r["po_revision"] for r in done if r.get("po_revision")]

    def usage_total(group: str, name: str, key: str) -> float:
        return sum(float(r.get(group, {}).get(name, {}).get(key, 0)) for r in records)

    n = len(records)
    total_cost = sum(usage_total("usage", t, "cost") for t in TIERS)
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
        "high_tp": tp, "high_fp": fp, "high_fn": fn,
        "match_accuracy": _ratio(sum(m["ok"] for m in matches), len(matches)) if matches else None,
        "match_questions": sum(m["asked"] for m in matches) if matches else None,
        "po_revision": _ratio(sum(r["expected"] == r["extracted"] for r in revisions), len(revisions)) if revisions else None,
        "drafts": len(drafts),
        "draft_values_checked": sum(d["checked"] for d in drafts),
        "draft_violations": sum(len(d["violations"]) for d in drafts),
        "drafts_clean": _ratio(sum(not d["violations"] for d in drafts), len(drafts)),
        "escalation_rate": _ratio(len(escalated), len(extracted)),
        "nano_alone": _ratio(len(extracted) - len(escalated), len(extracted)),
        "fields_escalated": len(escalations),
        "escalations_resolved": _ratio(sum(e["outcome"] == "resolved" for e in escalations), len(escalations)),
        "ultra_calls_per_assessed": _ratio(sum(r["usage"].get("ultra", {}).get("calls", 0) for r in assessed), len(assessed)),
        "risk_calls_per_assessed": _ratio(sum(r.get("stage_usage", {}).get("risk", {}).get("calls", 0) for r in assessed),
                                          len(assessed)),
        "assessed": len(assessed),
        "ultra_escalation_rate": (_ratio(sum(bool(x["escalated"]) for x in routed_runs), len(routed_runs))
                                  if routed_runs else None),
        "cost_per_email": _ratio(total_cost, n),
        "seconds_per_email": mean(r["seconds"] for r in records) if records else None,
        "total_cost": total_cost,
    }
    for tier in TIERS:
        out[f"{tier}_cost_per_email"] = _ratio(usage_total("usage", tier, "cost"), n)
        out[f"{tier}_calls_per_email"] = _ratio(usage_total("usage", tier, "calls"), n)
        out[f"{tier}_seconds_per_email"] = _ratio(usage_total("usage", tier, "latency_ms") / 1000, n)
    has_stages = any("stage_usage" in r for r in records)
    for stage in STAGES:
        out[f"{stage}_cost_per_email"] = _ratio(usage_total("stage_usage", stage, "cost"), n) if has_stages else None
        out[f"{stage}_seconds_per_email"] = (_ratio(usage_total("stage_usage", stage, "latency_ms") / 1000, n)
                                             if has_stages else None)
    out["risk_cost_per_assessed"] = _ratio(usage_total("stage_usage", "risk", "cost"), len(assessed)) if has_stages else None
    out["risk_seconds_per_assessed"] = (_ratio(usage_total("stage_usage", "risk", "latency_ms") / 1000, len(assessed))
                                        if has_stages else None)
    out["field_gain"] = out["fields"] - out["fields_before"] if out["fields"] is not None and out["fields_before"] is not None else None
    out["line_item_gain"] = (out["line_items"] - out["line_items_before"]
                             if out["line_items"] is not None and out["line_items_before"] is not None else None)
    return out


# Archived passes: (folder, split suffix). Current passes are in runs/ itself.
ARCHIVES = (
    ("m7", "@m7"),                     # Milestone 7
    ("before_routing", "@prev"),       # the step before Super became the default for risk
    ("test_v2_heldout", "@heldout"),   # TEST v2, run once while still held out
    ("routing_step", "@routing"),      # Super-default risk routing and the DEV fixes after TEST v2
)


def _load() -> dict[tuple[str, str], list[dict]]:
    """Runs grouped by (split, variant); archived runs get the split '<split><suffix>'."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for folder, suffix in ((RUNS_DIR, ""), *((RUNS_DIR / name, sfx) for name, sfx in ARCHIVES)):
        for path in sorted(folder.glob("*.json")):
            run = json.loads(path.read_text(encoding="utf-8"))
            if run.get("llm_mode") != "live" or run.get("cache"):
                continue
            groups[(run["split"] + suffix, run["variant"])].append(run)
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
    ("Order matching: email put on the right order", "match_accuracy", "pct"),
    ("Order matching: questions put to a person", "match_questions", "f1"),
    ("PO revision read from the PO number", "po_revision", "pct"),
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
    ("Emails that failed to process", "errors", "f1"),
]
# Rows added with Super-default risk routing (not in the held-out TEST v2 table, which is kept as published).
ROUTING_ROWS = [
    ("Risk runs escalated to Ultra", "ultra_escalation_rate", "pct"),
    ("Risk-stage cost per assessed email", "risk_cost_per_assessed", "usd"),
]
VARIANT_NAMES = {"routed": "Routed (ours)", "nano_only": "Nano only", "ultra_all": "Ultra for everything",
                 "super_risk": "Super for risk", "ultra_risk": "Ultra for risk"}


def build() -> str:
    groups = _load()
    per = {key: [metrics(run) for run in runs] for key, runs in groups.items()}

    def col(split: str, variant: str, key: str, kind: str) -> str:
        return _fmt([m[key] for m in per.get((split, variant), [])], kind)

    def runs(split: str, variant: str) -> int:
        return len(per.get((split, variant), []))

    def emails(split: str) -> int:
        return per[(split, "routed")][0]["emails"] if per.get((split, "routed")) else 0

    def spend(match) -> float:
        return sum(m["total_cost"] for key, ms in per.items() if match(key[0]) for m in ms)

    pre_fix = sum(metrics(json.loads(p.read_text(encoding="utf-8")))["total_cost"]
                  for p in sorted((RUNS_DIR / "pre_fix").glob("*.json")))
    lines = [
        "# ExportAgent evaluation report",
        "",
        f"DEV ({emails('dev')} cases) run {runs('dev', 'routed')}× with the final pipeline (evaluation frozen), "
        "end to end with the response cache off: classification and extraction, escalation, order matching and "
        "change detection, the risk agent (Super by default, Ultra on escalation), and drafts with the fact "
        "check. Values are mean (min–max) where there are several runs. TEST v2 was run three times while held "
        "out and once after the DEV-driven fixes; the held-out results below are kept exactly as first "
        "published, and TEST v2 was not run again after the two final fixes. TEST v1 has been seen since "
        "Milestone 7.",
        "",
        f"Model spend: final DEV pass **${spend(lambda s: '@' not in s):.2f}**; routing step (DEV and TEST v2 "
        f"after the fixes) **${spend(lambda s: s.endswith('@routing')):.2f}**; "
        f"TEST v2 held out **${spend(lambda s: s == 'test_v2@heldout'):.2f}**; the step before "
        f"**${spend(lambda s: s.endswith('@prev')) + pre_fix:.2f}**"
        + (f" (including ${pre_fix:.2f} for a DEV pass before its last fixes, kept in `runs/pre_fix/`)." if pre_fix else "."),
        "",
    ]
    if per.get(("test_v2@heldout", "routed")):
        lines += _test_v2(per, col, runs, emails, spend(lambda s: s == "test_v2@heldout"), groups)
    if per.get(("test_v2@routing", "routed")):
        lines += _test_v2_after(per, col, runs, groups)

    lines += [
        "## Results: routed setup",
        "",
        "DEV final adds case_033–035 (the two final fixes) to the 32 cases of the routing step; earlier "
        "columns are earlier versions of the pipeline on the cases DEV had then.",
        "",
    ]
    columns = [(f"DEV final ({emails('dev')} cases)", "dev"), (f"DEV routing step ({emails('dev@routing')})", "dev@routing"),
               (f"DEV before routing ({emails('dev@prev')})", "dev@prev"),
               ("DEV at M7 (10 cases)", "dev@m7"), ("TEST v1 after M7 fixes (seen)", "test@prev"),
               ("TEST v1 at M7 (held out)", "test@m7")]
    lines += ["| Metric | " + " | ".join(name for name, _ in columns) + " |", "|---|" + "---|" * len(columns)]
    for label, key, kind in MAIN_ROWS + ROUTING_ROWS:
        lines.append(f"| {label} | " + " | ".join(col(split, "routed", key, kind) for _, split in columns) + " |")

    lines += _risk_routing(per, col, groups)

    variants = {v: n for v, n in VARIANT_NAMES.items() if per.get(("dev@prev", v))}
    lines += [
        "",
        "## Cost per email by pipeline stage (DEV before this step, with drafts)",
        "",
        "Extraction = classify, extract, escalated re-extraction and stated-change detection; risk = the agent's "
        "planning and reasoning; drafting = the reply and the internal note. Averaged over all DEV emails "
        "(emails without an order skip risk; emails needing no reply skip drafting). These passes ran before "
        "this step, when routed meant Ultra for risk.",
        "",
        "| Stage | " + " | ".join(variants.values()) + " |",
        "|---|" + "---|" * len(variants),
    ]
    for stage in STAGES:
        lines.append(f"| {stage.capitalize()} | "
                     + " | ".join(col("dev@prev", v, f"{stage}_cost_per_email", "usd") for v in variants) + " |")
    lines.append("| **Total** | " + " | ".join(col("dev@prev", v, "cost_per_email", "usd") for v in variants) + " |")
    lines.append("| Model time, all stages | " + " | ".join(
        _fmt([sum(m[f"{s}_seconds_per_email"] or 0 for s in STAGES) for m in per.get(("dev@prev", v), [])], "s")
        for v in variants) + " |")

    quality_rows = [
        ("Field extraction accuracy", "fields", "pct"),
        ("Line-item accuracy", "line_items", "pct"),
        ("Change detection: recall", "change_recall", "pct"),
        ("High-risk flags: precision", "high_precision", "pct"),
        ("High-risk flags: recall", "high_recall", "pct"),
        ("Drafts with no violations", "drafts_clean", "pct"),
    ]
    lines += ["", "Quality of the same DEV passes:", "",
              "| Metric | " + " | ".join(variants.values()) + " |", "|---|" + "---|" * len(variants)]
    for label, key, kind in quality_rows:
        lines.append(f"| {label} | " + " | ".join(col("dev@prev", v, key, kind) for v in variants) + " |")

    lines += _super_vs_ultra(per, col)

    lines += [
        "",
        "## Cost and latency by model (routed, per email)",
        "",
        "| Model | DEV final cost | DEV final calls | DEV final model time | TEST v2 after fixes cost | TEST v2 after fixes calls |",
        "|---|---|---|---|---|---|",
    ]
    for tier in TIERS:
        lines.append(
            f"| {tier.capitalize()} | {col('dev', 'routed', f'{tier}_cost_per_email', 'usd')} "
            f"| {col('dev', 'routed', f'{tier}_calls_per_email', 'f1')} "
            f"| {col('dev', 'routed', f'{tier}_seconds_per_email', 's')} "
            f"| {col('test_v2@routing', 'routed', f'{tier}_cost_per_email', 'usd')} "
            f"| {col('test_v2@routing', 'routed', f'{tier}_calls_per_email', 'f1')} |"
        )

    lines += _per_case("DEV per case (routed, final)", groups.get(("dev", "routed"), []))
    lines += _per_case("TEST v1 per case (routed, after the M7 fixes)", groups.get(("test@prev", "routed"), []))
    if NOTES.exists():
        lines += ["", NOTES.read_text(encoding="utf-8").strip()]
    return "\n".join(lines) + "\n"


def _routing_reasons(runs: list[dict]) -> dict[str, int]:
    """How often each escalation trigger fired, over all runs (reason text up to the first colon)."""
    counts: dict[str, int] = defaultdict(int)
    for run in runs:
        for record in run["records"]:
            routing = (record.get("agent") or {}).get("routing") or {}
            for reason in routing.get("reasons") or []:
                counts[reason.split(":")[0].split("(")[0].strip()] += 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _risk_routing(per: dict, col, groups: dict) -> list[str]:
    lines = [
        "",
        "## Risk routing: Super by default, Ultra on escalation",
        "",
        "Measured in the routing step (3 DEV passes on 32 cases, before the two final fixes). Triggers (app/agent/routing.py): the current plan is infeasible; the email or thread mentions materials "
        "already available or a partial shipment; Super's flags conflict with the Python feasibility result; "
        "Super's report fails validation. The Ultra column re-runs DEV with risk always on Ultra (no drafts), "
        "for comparison on the same cases.",
        "",
        "| Metric | DEV: routed (Super + escalation) | DEV: Ultra always | TEST v2 after fixes: routed |",
        "|---|---|---|---|",
    ]
    rows = [
        ("Risk runs escalated to Ultra", "ultra_escalation_rate", "pct"),
        ("High-risk flags: precision", "high_precision", "pct"),
        ("High-risk flags: recall", "high_recall", "pct"),
        ("Risk-stage calls per assessed email", "risk_calls_per_assessed", "f1"),
        ("Risk-stage cost per assessed email", "risk_cost_per_assessed", "usd"),
        ("Risk-stage model time per assessed email", "risk_seconds_per_assessed", "s"),
        ("Emails assessed", "assessed", "n"),
    ]
    for label, key, kind in rows:
        lines.append(f"| {label} | {col('dev@routing', 'routed', key, kind)} | {col('dev@routing', 'ultra_risk', key, kind)} "
                     f"| {col('test_v2@routing', 'routed', key, kind)} |")
    lines += ["", "Cost per email by stage, this step (DEV with drafts; the Ultra-always pass ran without drafts):", "",
              "| Stage | DEV: routed | DEV: Ultra always | TEST v2 after fixes |", "|---|---|---|---|"]
    for stage in STAGES:
        lines.append(f"| {stage.capitalize()} | {col('dev@routing', 'routed', f'{stage}_cost_per_email', 'usd')} "
                     f"| {col('dev@routing', 'ultra_risk', f'{stage}_cost_per_email', 'usd')} "
                     f"| {col('test_v2@routing', 'routed', f'{stage}_cost_per_email', 'usd')} |")
    lines.append(f"| **Total** | {col('dev@routing', 'routed', 'cost_per_email', 'usd')} | {col('dev@routing', 'ultra_risk', 'cost_per_email', 'usd')} "
                 f"| {col('test_v2@routing', 'routed', 'cost_per_email', 'usd')} |")
    for name, split in (("DEV", "dev@routing"), ("TEST v2 after fixes", "test_v2@routing")):
        reasons = _routing_reasons(groups.get((split, "routed"), []))
        if reasons:
            total = sum(len(r["records"]) for r in groups.get((split, "routed"), []))
            lines += ["", f"Escalation triggers on {name} (count over all runs, {total} emails):", ""]
            lines += [f"- {reason}: {count}" for reason, count in reasons.items()]
    return lines


def _test_v2_after(per: dict, col, runs, groups: dict) -> list[str]:
    lines = [
        "## TEST v2 after DEV-driven fixes (seen)",
        "",
        "The same 30 cases, run once after this step's fixes. **This set is now seen**: its held-out results "
        "(above) showed which patterns fail; each fix was then written against new DEV cases (case_022–032) "
        "without changing any TEST v2 file. So this is a check that the fixes generalise, not a held-out score.",
        "",
        f"| Metric | After fixes ({runs('test_v2@routing', 'routed')} run) | Held out ({runs('test_v2@heldout', 'routed')} runs, above) |",
        "|---|---|---|",
    ]
    for label, key, kind in MAIN_ROWS + ROUTING_ROWS:
        lines.append(f"| {label} | {col('test_v2@routing', 'routed', key, kind)} | {col('test_v2@heldout', 'routed', key, kind)} |")
    lines += ["", "### Cost per email by stage, after fixes", "", "| Stage | After fixes | Held out |", "|---|---|---|"]
    for stage in STAGES:
        lines.append(f"| {stage.capitalize()} | {col('test_v2@routing', 'routed', f'{stage}_cost_per_email', 'usd')} "
                     f"| {col('test_v2@heldout', 'routed', f'{stage}_cost_per_email', 'usd')} |")
    lines.append(f"| **Total** | {col('test_v2@routing', 'routed', 'cost_per_email', 'usd')} "
                 f"| {col('test_v2@heldout', 'routed', 'cost_per_email', 'usd')} |")
    lines += _per_case("TEST v2 per case after fixes (routed)", groups.get(("test_v2@routing", "routed"), []))
    return lines + [""]


def _test_v2(per: dict, col, runs, emails, spend: float, groups: dict) -> list[str]:
    """The held-out TEST v2 results, first in the report."""
    lines = [
        "## TEST v2 (held out)",
        "",
        f"{emails('test_v2@heldout')} cases (t2_001–t2_030), all written by a separate assistant session from "
        "[TEST_V2_SPEC.md](TEST_V2_SPEC.md) alone; the build assistant validated structure only. Committed before "
        "any run (commit `24f19ae`). Routed setup run "
        f"{runs('test_v2@heldout', 'routed')}×, Super for risk {runs('test_v2@heldout', 'super_risk')}×, end to end with the cache "
        "off and drafts on. No code or prompt was changed after the set was seen. "
        f"Model spend on TEST v2: **${spend:.2f}**.",
        "",
        "| Metric | Routed (ours) | Super for risk |",
        "|---|---|---|",
    ]
    for label, key, kind in MAIN_ROWS:
        lines.append(f"| {label} | {col('test_v2@heldout', 'routed', key, kind)} | {col('test_v2@heldout', 'super_risk', key, kind)} |")
    lines += [
        "",
        "### TEST v2 cost per email by stage",
        "",
        "| Stage | Routed (ours) | Super for risk |",
        "|---|---|---|",
    ]
    for stage in STAGES:
        lines.append(f"| {stage.capitalize()} | {col('test_v2@heldout', 'routed', f'{stage}_cost_per_email', 'usd')} "
                     f"| {col('test_v2@heldout', 'super_risk', f'{stage}_cost_per_email', 'usd')} |")
    lines.append(f"| **Total** | {col('test_v2@heldout', 'routed', 'cost_per_email', 'usd')} "
                 f"| {col('test_v2@heldout', 'super_risk', 'cost_per_email', 'usd')} |")
    for stage in STAGES:
        lines.append(f"| Model time: {stage} | {col('test_v2@heldout', 'routed', f'{stage}_seconds_per_email', 's')} "
                     f"| {col('test_v2@heldout', 'super_risk', f'{stage}_seconds_per_email', 's')} |")
    lines += _per_case("TEST v2 per case (routed)", groups.get(("test_v2@heldout", "routed"), []))
    return lines + [""]


def _super_vs_ultra(per: dict, col) -> list[str]:
    rows = [
        ("High-risk flags: precision", "high_precision", "pct"),
        ("High-risk flags: recall", "high_recall", "pct"),
        ("High-risk flags: true / false positives / missed", None, None),
        ("Risk-stage calls per assessed email", "risk_calls_per_assessed", "f1"),
        ("Risk-stage cost per assessed email", "risk_cost_per_assessed", "usd"),
        ("Risk-stage model time per assessed email", "risk_seconds_per_assessed", "s"),
        ("Emails assessed", "assessed", "n"),
    ]
    lines = [
        "",
        "## Risk agent: Super instead of Ultra",
        "",
        "Same pipeline, same pre-fetch and tools; only the planning and risk-reasoning calls move from Ultra to "
        "Super. One Super pass per split; the Ultra columns are the routed passes. These ran before this step "
        "(when routed meant Ultra for risk) and led to Super becoming the default.",
        "",
        "| Metric | DEV: Ultra | DEV: Super | TEST v1: Ultra | TEST v1: Super | TEST v2: Ultra | TEST v2: Super |",
        "|---|---|---|---|---|---|---|",
    ]

    def counts(split: str, variant: str) -> str:
        ms = per.get((split, variant), [])
        return " / ".join(f"{m['high_tp']}/{m['high_fp']}/{m['high_fn']}" for m in ms) or "n/a"

    for label, key, kind in rows:
        if key is None:
            cells = [counts(s, v) for s in ("dev@prev", "test@prev", "test_v2@heldout") for v in ("routed", "super_risk")]
        else:
            cells = [col(s, v, key, kind) for s in ("dev@prev", "test@prev", "test_v2@heldout") for v in ("routed", "super_risk")]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines


def _per_case(title: str, runs: list[dict]) -> list[str]:
    if not runs:
        return []
    lines = [
        "",
        f"## {title}",
        "",
        "Field and line-item accuracy averaged over the runs; order matching and high-risk groups per run.",
        "",
        "| Case | Fields | Line items | Right order | Changes found | Expected high | Predicted high per run | Draft violations |",
        "|---|---|---|---|---|---|---|---|",
    ]
    by_case: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        for record in run["records"]:
            by_case[record["case_id"]].append(record)
    for case_id in sorted(by_case):
        records = [r for r in by_case[case_id] if "error" not in r]
        if not records:
            lines.append(f"| {case_id} | error | | | | | | |")
            continue
        fields = [ok for r in records for ok in r["score"]["fields"].values()]
        items = sum(r["score"]["line_items_correct"] for r in records), sum(r["score"]["line_items_total"] for r in records)
        changes = sum(r["changes"]["correct"] for r in records), sum(r["changes"]["expected"] for r in records)
        violations = sum(len(d["violations"]) for r in records for d in r.get("drafts", []))
        matched = [r["match"] for r in records if r.get("match")]
        match_cell = " / ".join(("yes" if m["ok"] else "no") + (" (asked)" if m["asked"] else "") for m in matched) or "–"
        lines.append(
            f"| {case_id} | {_fmt([_ratio(sum(fields), len(fields))], 'pct') if fields else '–'} "
            f"| {_fmt([_ratio(*items)], 'pct') if items[1] else '–'} "
            f"| {match_cell} "
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
