"""Run the six scenario emails through "Try your own email" on the live site, one by one.

For each email: submit the form, wait until the page has finished analysis, the risk step
(when the email belongs to an order) and the drafts, then save full-page screenshots and the
API's view of the result (classification, fields, order and versions, risk run, drafts,
match questions, and the model calls made for this email) to results/<T>.json.

    PLAYWRIGHT_BROWSERS_PATH=... python run_scenarios.py <scenarios.txt> [base-url]
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
SCEN = Path(sys.argv[1])
BASE = sys.argv[2] if len(sys.argv) > 2 else "https://3-104-80-176.sslip.io"
SHOTS = HERE / "screenshots"
RESULTS = HERE / "results"
PIPELINE_TEXTS = ("Reading the email:", "Checking the risk:", "Drafting the reply")


def parse(text: str) -> list[dict]:
    """=== T1 === blocks with From:, Subject: and a body."""
    out = []
    for name, block in re.findall(r"=== (T\d) ===\n(.*?)(?=\n=== T\d ===|\Z)", text, re.S):
        sender = re.search(r"^From: (.*)$", block, re.M).group(1).strip()
        subject = re.search(r"^Subject: (.*)$", block, re.M).group(1).strip()
        body = block.split("\n", 2)[2].strip("\n") if block.startswith("From:") else block
        body = re.sub(r"\A(From:.*\n)?(Subject:.*\n)?\n?", "", block).strip("\n")
        out.append({"name": name, "sender": sender, "subject": subject, "body": body})
    return out


def main():
    SHOTS.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    scenarios = parse(SCEN.read_text(encoding="utf-8"))
    assert [s["name"] for s in scenarios] == ["T1", "T2", "T3", "T4", "T5", "T6"], [s["name"] for s in scenarios]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        # The link from here to Sydney can be slow (several seconds per request): be patient.
        page.set_default_timeout(120000)
        page.set_default_navigation_timeout(120000)
        api = page.request

        def get(path):
            r = api.get(BASE + path)
            return r.json() if r.ok else {"_status": r.status, "_text": r.text()[:300]}

        start_summary = get("/api/trace/summary")
        state = {"emails": get("/api/emails"), "orders": get("/api/orders"), "health": get("/health")}
        (RESULTS / "state_before.json").write_text(json.dumps(state, indent=1, default=str))
        page.goto(BASE + "/", wait_until="load")
        page.wait_for_timeout(4000)
        page.screenshot(path=str(SHOTS / "00_dashboard_before.png"), full_page=True)

        for s in scenarios:
            last_call = max((c["id"] for c in get("/api/trace/calls?limit=1")), default=0)
            page.goto(BASE + "/try", wait_until="load")
            page.get_by_placeholder("Name <name@buyer.com>").wait_for()
            page.get_by_placeholder("Name <name@buyer.com>").fill(s["sender"])
            page.get_by_placeholder("New PO 4471").fill(s["subject"])
            page.get_by_placeholder(re.compile("Paste the buyer's email")).fill(s["body"])
            t0 = time.time()
            page.locator('button[type="submit"]').click()
            page.wait_for_url(re.compile(r"/emails/\d+"), timeout=120000)
            email_id = int(re.search(r"/emails/(\d+)", page.url).group(1))
            # Done when the page has shown its pipeline and no stage message remains.
            page.wait_for_function(
                """(texts) => { const t = document.body.innerText;
                     return t.includes('CLASSIFICATION') || t.includes('Classification') ? !texts.some(x => t.includes(x)) : false; }""",
                arg=list(PIPELINE_TEXTS), timeout=420000, polling=1000)
            page.wait_for_timeout(2500)
            elapsed = round(time.time() - t0, 1)
            page.screenshot(path=str(SHOTS / f"{s['name']}_email.png"), full_page=True)

            email = get(f"/api/emails/{email_id}")
            run = get(f"/api/emails/{email_id}/agent") if email.get("order_id") else None
            drafts = get(f"/api/emails/{email_id}/drafts")
            order = get(f"/api/orders/{email['order_id']}") if email.get("order_id") else None
            if order:
                page.goto(f"{BASE}/orders/{email['order_id']}", wait_until="load")
                page.wait_for_timeout(4000)
                page.screenshot(path=str(SHOTS / f"{s['name']}_order.png"), full_page=True)
            calls = [c for c in get("/api/trace/calls?limit=200") if c["id"] > last_call]
            result = {
                "scenario": s, "email_id": email_id, "elapsed_s": elapsed, "email": email, "order": order,
                "agent_run": run, "drafts": drafts, "match_questions": get("/api/match-questions"),
                "calls": calls,
                "cost_usd": round(sum(float(c["cost_usd"]) for c in calls), 6),
                "model_latency_ms": sum(c["latency_ms"] for c in calls),
            }
            (RESULTS / f"{s['name']}.json").write_text(json.dumps(result, indent=1, default=str))
            print(f"{s['name']}: email {email_id}, {elapsed}s, {len(calls)} calls, ${result['cost_usd']}", flush=True)

        page.goto(BASE + "/", wait_until="load")
        page.wait_for_timeout(4000)
        page.screenshot(path=str(SHOTS / "99_dashboard_after.png"), full_page=True)
        end_summary = get("/api/trace/summary")
        (RESULTS / "spend.json").write_text(json.dumps({"before": start_summary, "after": end_summary}, indent=1))
        print("spent today before/after:", start_summary["spent_today_usd"], end_summary["spent_today_usd"])
        browser.close()


if __name__ == "__main__":
    main()
