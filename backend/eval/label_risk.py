"""Expected high-risk groups per case, derived from the hand-written labels (never from app output).

The labels give the true order after every email; this replays them in arrival order and
applies the severity rubric with the same capacity model and policy as the app:

  schedule  the order's current plan is infeasible under the factory profile, given the other
            orders known on the email's date
  value     the contract value changed by more than the policy threshold (percentage, or the
            absolute threshold converted to USD)

Label keys used here (all optional):
  revises:      the earlier case about the same order (otherwise the labelled PO number links them)
  true_state:   values of the true order that the email does not state (e.g. the new total after
                a partial update: {total_quantity: 2100})
  fabric_ready: true when the thread says fabric is already in-house

Usage (from backend/):  python -m eval.label_risk --split test_v2 [--write]
--write adds expected_high_risk and risk_note to labels that do not have them yet.
"""

import argparse
import sys
from copy import deepcopy
from datetime import date
from typing import Any

from app.agent.tools.feasibility import check_feasibility
from app.config import get_settings
from app.services.order_matching import po_key
from app.services.profiles import load_profile
from app.services.risk_policy import contract_value_change, is_high_value_change, load_policy
from eval.dataset import EVAL_DIR, SPLITS, load_cases, load_expected

SCALARS = ("buyer", "po_number", "style", "currency", "unit_price", "total_quantity", "delivery_date",
           "incoterms", "port", "destination_country")
# True order state for TEST v1 partial updates, written before these keys existed in labels.
_LEGACY_TRUE_STATE = {"test_019": {"total_quantity": 3000}, "test_025": {"total_quantity": 4500}}
_LEGACY_FABRIC_READY = {"case_007"}


def derive(split: str) -> dict[str, dict[str, Any]]:
    profile = load_profile(get_settings().factory_profile)
    policy = load_policy()
    cases = sorted(load_cases(split), key=lambda c: (c.received_at, c.id))
    store: dict[str, dict] = {}        # order key -> latest true snapshot
    known: dict[str, date] = {}        # order key -> date of its first email
    order_of: dict[str, str] = {}      # case -> order key
    results = {}
    for case in cases:
        label = load_expected(case.id)
        extraction = label.get("extraction")
        if not extraction:
            results[case.id] = {"high": [], "note": "no order"}
            continue
        po = extraction.get("po_number")
        key = order_of.get(label.get("revises")) or (po_key(po) if po else case.id)
        order_of[case.id] = key
        update = {k: extraction.get(k) for k in SCALARS}
        previous = store.get(key)
        if previous is None:
            baseline = None
            # a reply thread quoting an earlier value of an order not seen before
            for change in label.get("expected_changes") or []:
                if change["field"] == "delivery_date":
                    baseline = {**update, "delivery_date": change["old"]}
            current = deepcopy(update)
        else:
            baseline = previous
            current = deepcopy(previous)
            current.update({k: v for k, v in update.items() if v is not None})
        current.update(label.get("true_state") or _LEGACY_TRUE_STATE.get(case.id, {}))
        store[key] = current
        known.setdefault(key, case.received_at)

        high, notes = [], []
        if current.get("delivery_date") and current.get("total_quantity"):
            due = date.fromisoformat(str(current["delivery_date"]))
            load = sum(
                int(o["total_quantity"]) for other, o in store.items()
                if other != key and known[other] <= case.received_at and o.get("delivery_date") and o.get("total_quantity")
                and case.received_at < date.fromisoformat(str(o["delivery_date"])) <= due
            )
            result = check_feasibility(
                quantity=int(current["total_quantity"]), delivery_date=due, as_of=case.received_at, profile=profile,
                other_orders_load=load,
                fabric_ready=bool(label.get("fabric_ready")) or case.id in _LEGACY_FABRIC_READY,
            )
            notes.append(f"{result.verdict}: {result.reason}")
            if result.verdict == "infeasible":
                high.append("schedule")
        if baseline is not None:
            change = contract_value_change(baseline, current)
            if change:
                notes.append(f"value {change['change_pct']:+}% ({change['change']} {current.get('currency') or ''})".strip())
                if is_high_value_change(change, policy):
                    high.append("value")
        results[case.id] = {"high": high, "note": " | ".join(notes)}
    return results


def _write(split: str, results: dict[str, dict]) -> None:
    for case_id, result in results.items():
        path = next(p for p in (EVAL_DIR / split / "expected").glob(f"{case_id}.*"))
        text = path.read_text(encoding="utf-8")
        if "expected_high_risk" in text or path.suffix == ".json":
            continue
        note = result["note"].replace('"', "'")
        path.write_text(text.rstrip("\n") + f'\n\nexpected_high_risk: [{", ".join(result["high"])}]\nrisk_note: "{note}"\n',
                        encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=list(SPLITS), required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    results = derive(args.split)
    for case_id, result in sorted(results.items()):
        stated = load_expected(case_id).get("expected_high_risk")
        mark = "" if stated is None or sorted(stated) == sorted(result["high"]) else f"  (label says {stated})"
        print(f"{case_id}: {result['high']}{mark}  {result['note']}")
    if args.write:
        _write(args.split, results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
