"""Print a compact summary of results/T*.json (used to write REPORT.md)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def fields(extraction):
    out = {}
    for name, f in (extraction.get("fields") or {}).items():
        if isinstance(f, dict):
            out[name] = (f.get("value"), f.get("confidence"))
    return out


for name in sys.argv[1:] or ["T1", "T2", "T3", "T4", "T5", "T6"]:
    r = json.loads((HERE / "results" / f"{name}.json").read_text())
    e = r["email"]
    c = e.get("classification") or {}
    x = e.get("extraction") or {}
    print(f"===== {name}: email {r['email_id']}, {r['elapsed_s']} s end to end, {len(r['calls'])} model calls, ${r['cost_usd']}")
    print("status:", e.get("status"), "| order_id:", e.get("order_id"), "| notice:", e.get("notice"), "| error:", e.get("analysis_error"))
    print("classification:", c.get("category"), c.get("intents"), "has_po_data", c.get("has_po_data"), "conf", c.get("confidence"))
    print("summary:", c.get("summary"))
    for k, v in fields(x).items():
        print(f"   {k}: {v[0]!r} ({v[1]})")
    print("review:", json.dumps(x.get("review"), default=str)[:700])
    print("escalations:", json.dumps(x.get("escalations"), default=str)[:400])
    print("notes:", json.dumps(x.get("notes"), default=str)[:300], "| inherited:", x.get("inherited"))
    if r["order"]:
        o = r["order"]
        print("order:", o["id"], o["po_number"], o["buyer"], o["style"], "status", o["status"], "versions", len(o["versions"]))
        for v in o["versions"]:
            mine = " <- this email" if v["email_id"] == r["email_id"] else ""
            print(f"   v{v['version']} ({v['basis']}){mine}: qty {v['data'].get('total_quantity')} date {v['data'].get('delivery_date')} "
                  f"price {v['data'].get('unit_price')} {v['data'].get('currency')} rev {v['data'].get('po_revision')}")
            for ch in v.get("changes") or []:
                print(f"      change: {ch.get('field')} {ch.get('old')} -> {ch.get('new')} {ch.get('alert') or ''} | {ch.get('summary', '')[:90]}")
    mq = [q for q in (r["match_questions"] or []) if isinstance(q, dict) and q.get("email_id") == r["email_id"]]
    print("match questions for this email:", json.dumps(mq, default=str)[:400])
    run = r["agent_run"]
    if run:
        res = run.get("result") or {}
        print("risk:", run.get("status"), "| error:", run.get("error"), "| notice:", run.get("notice"))
        print("routing:", res.get("routing"))
        print("summary:", res.get("summary"))
        for f in res.get("flags", []):
            print(f"   FLAG {f['severity'].upper()} {f['category']}: {f['reason'][:160]} | ev {f.get('evidence')}")
        for i in res.get("info_checked", []):
            print(f"   info {i['topic']}: {i['finding'][:140]} | ev {i.get('evidence')}")
        for s in run.get("steps", []):
            if s["name"] in ("check_compliance", "lookup_buyer"):
                srcs = (s.get("output") or {}).get("sources") or []
                print(f"   {s['name']} {s.get('evidence_id')}: {len(srcs)} sources: " + "; ".join(x.get('url', '')[:70] for x in srcs[:4]))
            if s["kind"] == "routing" or s["name"] == "check_delivery_feasibility":
                print(f"   step {s['name']} r{s['round']}: {(s.get('summary') or '')[:150]} | in {json.dumps(s.get('input'))[:120]}")
    for d in r["drafts"] if isinstance(r["drafts"], list) else []:
        print(f"--- draft {d['kind']} ({d['model']}, ${d['cost_usd']}): checked {d.get('checked')} violations {d.get('violations')}")
        print("   " + (d.get("body") or d.get("text") or "").replace("\n", "\n   ")[:1600])
    tiers = {}
    for call in r["calls"]:
        tiers.setdefault(f"{call['task_type']}:{call['tier']}:{call['source']}", 0)
        tiers[f"{call['task_type']}:{call['tier']}:{call['source']}"] += 1
    print("calls:", tiers, "| failed calls:", [c["error"][:80] for c in r["calls"] if not c["success"]])
    print()
