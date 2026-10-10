"""One evaluation pass: every case of a split, end to end, scored against the labels.

Each pass uses a fresh scratch database, so the order store, the risk agent and the
drafts see only that split's emails, in the order they arrived. The response cache is
off by default, so repeated passes measure real model behaviour, cost and latency.

Variants:
  routed     the production setup: Nano extracts, Super re-extracts failing fields and
             drafts, Ultra assesses risk
  nano_only  baseline: every task on Nano, no escalation
  ultra_all  baseline: every task on Ultra

Usage (from backend/):
  python -m eval.run_eval --split test --variant routed --run 1 [--no-drafts]
Writes eval/runs/<split>-<variant>-<run>.json; eval/report.py turns the runs into REPORT.md.
"""

import argparse
import json
import sys
import tempfile
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from datetime import time as clock
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.agent.loop import run_agent
from app.agent.tools.diff_po_versions import plan_versions, snapshot_from_extraction
from app.config import get_settings
from app.db import Base, SessionLocal
from app.llm.router import LLMError, LLMRouter
from app.llm.tasks import Tier
from app.models import Email, EmailAttachment, LLMCall, SearchCache
from app.services.analysis import Analysis, analyse_email
from app.services.drafting import DraftingError, generate_drafts
from app.services.orders import normalise_po_number
from eval.dataset import EVAL_DIR, Case, load_cases, load_expected
from eval.scoring import score_case, score_changes

RUNS_DIR = EVAL_DIR / "runs"
VARIANTS = {
    "routed": {},
    "nano_only": {"llm_force_tier": Tier.NANO, "escalation_enabled": False},
    "ultra_all": {"llm_force_tier": Tier.ULTRA},
}
# Which risk group a high flag of each category counts towards.
_HIGH_GROUPS = {"delivery": "schedule", "capacity": "schedule", "price": "value", "quantity": "value"}


def predict_changes(store: dict[str, dict], analysis: Analysis) -> list:
    """The same versioning the order store applies, kept in memory."""
    if not analysis.extraction or not analysis.extraction.fields.po_number.value:
        return []
    key = normalise_po_number(analysis.extraction.fields.po_number.value)
    planned = plan_versions(store.get(key), snapshot_from_extraction(analysis.extraction.fields), analysis.stated_changes)
    if planned:
        store[key] = planned[-1].data
    return [change for version in planned for change in version.changes]


def high_groups(flags: list[dict]) -> list[str]:
    """Risk groups of the high flags; a high flag outside the rubric's groups counts as 'other'."""
    return sorted({_HIGH_GROUPS.get(f["category"], "other") for f in flags if f["severity"] == "high"})


def _plain(value: Any) -> Any:
    return json.loads(json.dumps(value, default=lambda v: sorted(v) if isinstance(v, set) else str(v)))


def _calls(session, after_id: int, until_id: int) -> list[LLMCall]:
    return session.scalars(select(LLMCall).where(LLMCall.id > after_id, LLMCall.id <= until_id)).all()


def _max_id(session) -> int:
    return session.scalar(select(func.coalesce(func.max(LLMCall.id), 0)))


def _usage(calls: list[LLMCall]) -> dict[str, dict]:
    usage: dict[str, dict] = {}
    for call in calls:
        tier = usage.setdefault(call.tier, {"calls": 0, "cost": Decimal(0), "latency_ms": 0,
                                           "input_tokens": 0, "output_tokens": 0, "failed": 0})
        tier["calls"] += 1
        tier["cost"] += call.cost_usd
        tier["latency_ms"] += call.latency_ms
        tier["input_tokens"] += call.input_tokens
        tier["output_tokens"] += call.output_tokens
        tier["failed"] += 0 if call.success else 1
    return usage


def run_pass(cases: list[Case], variant: str, *, drafts: bool, cache: bool) -> dict[str, Any]:
    settings = get_settings().model_copy(update={
        **VARIANTS[variant],
        "llm_cache_enabled": cache,
        # Spend is tracked per scratch database; the milestone budget is watched outside.
        "daily_spend_cap_usd": Decimal("100"),
    })
    scratch_dir = tempfile.mkdtemp(prefix="exportagent-eval-")
    engine = create_engine(f"sqlite:///{Path(scratch_dir, 'eval.db').as_posix()}")
    Base.metadata.create_all(engine)
    Scratch = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as main, Scratch() as scratch:
        for row in main.scalars(select(SearchCache)):
            scratch.merge(SearchCache(key=row.key, query=row.query, response=row.response))
        scratch.commit()

    router = LLMRouter(settings, session_factory=Scratch, cache_session_factory=SessionLocal)
    store: dict[str, dict] = {}
    records = []
    with Scratch() as session:
        for case in sorted(cases, key=lambda c: (c.received_at, c.id)):
            expected = load_expected(case.id)
            record: dict[str, Any] = {"case_id": case.id}
            first_call = _max_id(session)
            started = time.perf_counter()
            email = Email(
                external_id=case.id, sender=case.sender, subject=case.subject, body=case.body,
                received_at=datetime.combine(case.received_at, clock(9, 0), tzinfo=UTC), source="eval",
                attachments=[EmailAttachment(filename=a["filename"], content_type=a["content_type"],
                                             text_content=a["text"]) for a in case.attachments],
            )
            session.add(email)
            session.commit()
            try:
                analysis = analyse_email(session, email, router)
                if analysis is None:
                    raise LLMError(email.analysis_error or "analysis failed")
                nano_only = replace(analysis, extraction=analysis.extraction_before_escalation)
                record["score"] = asdict(score_case(case.id, expected, analysis))
                record["score_before_escalation"] = asdict(score_case(case.id, expected, nano_only))
                record["changes"] = asdict(score_changes(
                    case.id, expected.get("expected_changes") or [], predict_changes(store, analysis)))
                record["has_extraction"] = analysis.extraction is not None
                record["escalations"] = [e.model_dump(mode="json") for e in analysis.extraction.escalations] \
                    if analysis.extraction else []
                record["extracted"] = analysis.extraction.fields.model_dump(mode="json") if analysis.extraction else None
                record["classification"] = analysis.classification.model_dump(mode="json")

                record["expected_high"] = expected.get("expected_high_risk", [])
                record["predicted_high"] = []
                if email.order_id is not None:
                    run = run_agent(session, email, router)
                    flags = (run.result or {}).get("flags", [])
                    record["agent"] = {
                        "status": run.status, "rounds": run.rounds, "error": run.error,
                        "flags": flags, "info_checked": len((run.result or {}).get("info_checked", [])),
                        "tools": [f"{s.name}{' (0)' if s.round == 0 else ''}" for s in run.steps if s.kind == "tool"],
                    }
                    record["predicted_high"] = high_groups(flags)

                if drafts:
                    try:
                        written = generate_drafts(session, email, router)
                    except DraftingError as exc:
                        written, record["drafts_skipped"] = [], str(exc)
                    record["drafts"] = [
                        {"kind": d.kind, "words": len(d.body.split()), "checked": (d.fact_check or {}).get("checked", 0),
                         "violations": (d.fact_check or {}).get("violations", []), "text": d.body}
                        for d in written
                    ]
            except LLMError as exc:
                record["error"] = str(exc)[:500]
            record["seconds"] = round(time.perf_counter() - started, 2)
            record["usage"] = _usage(_calls(session, first_call, _max_id(session)))
            records.append(record)
            cost = sum((u["cost"] for u in record["usage"].values()), Decimal(0))
            print(f"{case.id}: {record['seconds']:.1f}s ${cost:.4f}" + (f" ERROR {record['error'][:80]}" if "error" in record else ""),
                  flush=True)

        with SessionLocal() as main:
            for row in session.scalars(select(SearchCache)):
                main.merge(SearchCache(key=row.key, query=row.query, response=row.response))
            main.commit()
    engine.dispose()
    return {"records": records}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="routed")
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--no-drafts", action="store_true")
    parser.add_argument("--cache", action="store_true", help="reuse cached responses (not for measurement)")
    args = parser.parse_args()

    settings = get_settings()
    started = datetime.now(UTC)
    result = run_pass(load_cases(args.split), args.variant, drafts=not args.no_drafts, cache=args.cache)
    result |= {
        "split": args.split, "variant": args.variant, "run": args.run, "llm_mode": settings.llm_mode,
        "cache": args.cache, "drafts": not args.no_drafts, "started": started.isoformat(),
        "finished": datetime.now(UTC).isoformat(),
        "models": {tier.value: settings.model_for(tier) for tier in Tier},
    }
    RUNS_DIR.mkdir(exist_ok=True)
    out = RUNS_DIR / f"{args.split}-{args.variant}-{args.run}.json"
    out.write_text(json.dumps(_plain(result), indent=1), encoding="utf-8")
    total = sum(Decimal(str(u["cost"])) for r in result["records"] for u in r["usage"].values())
    print(f"\nWritten {out} (cost ${total:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
