from eval.report import _fmt, metrics
from eval.run_eval import high_groups


def _record(case_id, *, fields, items=(0, 0), changes=(0, 0, 0), expected_high=(), predicted_high=(),
            escalations=(), drafts=(), ultra_calls=0, cost=0.01, seconds=10.0, agent=True):
    record = {
        "case_id": case_id,
        "score": {"category_ok": True, "intents_ok": False, "has_po_data_ok": True, "fields": fields,
                  "line_items_correct": items[0], "line_items_total": items[1],
                  "review_expected": ["po_number"], "review_flagged": ["po_number", "port"]},
        "score_before_escalation": {"category_ok": True, "intents_ok": False, "has_po_data_ok": True,
                                    "fields": {k: False for k in fields}, "line_items_correct": 0,
                                    "line_items_total": items[1], "review_expected": [], "review_flagged": []},
        "changes": {"correct": changes[0], "expected": changes[1], "predicted": changes[2]},
        "has_extraction": True,
        "escalations": list(escalations),
        "expected_high": list(expected_high),
        "predicted_high": list(predicted_high),
        "drafts": list(drafts),
        "seconds": seconds,
        "usage": {"nano": {"calls": 2, "cost": cost, "latency_ms": 2000},
                  "ultra": {"calls": ultra_calls, "cost": 0.02 * ultra_calls, "latency_ms": 3000 * ultra_calls}},
    }
    if agent:
        record["agent"] = {"flags": []}
    return record


def test_high_flags_map_to_risk_groups():
    flags = [
        {"severity": "high", "category": "delivery"},
        {"severity": "high", "category": "capacity"},
        {"severity": "high", "category": "price"},
        {"severity": "high", "category": "compliance"},
        {"severity": "medium", "category": "quantity"},
    ]

    assert high_groups(flags) == ["other", "schedule", "value"]


def test_metrics_from_records():
    run = {"records": [
        _record("a", fields={"buyer": True, "po_number": True}, items=(2, 3), changes=(1, 2, 1),
                expected_high=["schedule"], predicted_high=["schedule", "value"],
                escalations=[{"outcome": "resolved", "cost_usd": "0.001"}],
                drafts=[{"checked": 5, "violations": []}, {"checked": 3, "violations": [{"text": "x"}]}],
                ultra_calls=2),
        _record("b", fields={"buyer": True, "po_number": False}, items=(1, 1),
                expected_high=["value"], predicted_high=[], ultra_calls=1),
        {"case_id": "c", "error": "boom", "seconds": 1.0, "usage": {}},
    ]}

    m = metrics(run)

    assert (m["emails"], m["errors"]) == (3, 1)
    assert m["fields"] == 3 / 4 and m["fields_before"] == 0
    assert m["line_items"] == 3 / 4 and m["line_item_gain"] == 3 / 4
    assert (m["change_recall"], m["change_precision"]) == (1 / 2, 1.0)
    assert (m["high_precision"], m["high_recall"]) == (1 / 2, 1 / 2)
    assert (m["drafts"], m["draft_violations"], m["drafts_clean"]) == (2, 1, 1 / 2)
    assert (m["escalation_rate"], m["escalations_resolved"]) == (1 / 2, 1.0)
    assert m["ultra_calls_per_assessed"] == 3 / 2
    assert m["review_recall"] == 1.0 and m["review_precision"] == 1 / 2
    assert round(m["cost_per_email"], 4) == round((0.01 + 0.04 + 0.01 + 0.02) / 3, 4)


def test_format_mean_and_range():
    assert _fmt([0.9, 1.0, 0.95], "pct") == "95.0% (90.0%–100.0%)"
    assert _fmt([0.0123], "usd") == "$0.0123"
    assert _fmt([None], "pct") == "n/a"
