# ExportAgent evaluation report

Routed setup run 3× on DEV (10 cases) and 3× on TEST (30 held-out cases), end to end with the response cache off: classification and extraction, escalation, the order store and change detection, the risk agent, and drafts with the fact check. Values are mean (min–max) across runs. Baselines ran once on TEST.

Model spend in these runs: **$2.44**.

## Results: routed setup

| Metric | DEV | TEST |
|---|---|---|
| Classification: main category | 96.7% (90.0%–100.0%) | 95.6% (93.3%–96.7%) |
| Classification: all intents (exact set) | 70.0% (60.0%–80.0%) | 92.2% (90.0%–93.3%) |
| Classification: has PO data | 100.0% (100.0%–100.0%) | 94.4% (93.3%–96.7%) |
| Field extraction accuracy (after escalation) | 97.8% (96.6%–98.9%) | 91.9% (91.4%–92.6%) |
| Line-item accuracy (colour, quantity, sizes) | 88.9% (87.5%–91.7%) | 88.7% (88.7%–88.7%) |
| Human-review flags: recall | 100.0% (100.0%–100.0%) | 33.3% (33.3%–33.3%) |
| Human-review flags: precision | 100.0% (100.0%–100.0%) | 8.5% (8.3%–8.7%) |
| Change detection: recall | 100.0% (100.0%–100.0%) | 28.2% (23.1%–34.6%) |
| Change detection: precision | 100.0% (100.0%–100.0%) | 63.1% (50.0%–70.0%) |
| High-risk flags: precision | 100.0% (100.0%–100.0%) | 78.0% (76.9%–78.6%) |
| High-risk flags: recall | 100.0% (100.0%–100.0%) | 66.7% (62.5%–68.8%) |
| Drafts written | 18 (18–18) | 52 (52–52) |
| Draft values fact-checked | 129 (123–141) | 313 (299–327) |
| Draft fact-check violations | 0.0 (0.0–0.0) | 0.7 (0.0–1.0) |
| Drafts with no violations | 100.0% (100.0%–100.0%) | 98.7% (98.1%–100.0%) |
| Escalation rate (emails with an escalated field) | 33.3% (33.3%–33.3%) | 23.3% (20.8%–25.0%) |
| Emails handled by Nano alone | 66.7% (66.7%–66.7%) | 76.7% (75.0%–79.2%) |
| Escalations resolved by Super | 100.0% (100.0%–100.0%) | 100.0% (100.0%–100.0%) |
| Escalation gain: field accuracy | +3.0 pp (+2.2 pp–+3.4 pp) | +1.3 pp (+0.8 pp–+2.0 pp) |
| Escalation gain: line-item accuracy | +12.5 pp (+12.5 pp–+12.5 pp) | +5.0 pp (+1.9 pp–+9.4 pp) |
| Ultra calls per assessed email | 2.4 (2.1–2.8) | 2.6 (2.3–2.8) |
| Cost per email (all models) | $0.0169 ($0.0145–$0.0191) | $0.0157 ($0.0144–$0.0165) |
| Latency per email (wall clock, end to end) | 24.2 s (20.8 s–25.9 s) | 28.0 s (26.8 s–28.8 s) |
| Emails that failed to process | 0 (0–0) | 0 (0–0) |

## Cost and latency by model (routed, per email)

Per email over all emails in the split (emails without an order make no Ultra call). Latency here is the sum of model-call time; the table above is wall clock including search and database work.

| Model | DEV cost | TEST cost | DEV calls | TEST calls | DEV model time | TEST model time |
|---|---|---|---|---|---|---|
| Nano | $0.0003 ($0.0003–$0.0003) | $0.0002 ($0.0002–$0.0002) | 2.3 (2.2–2.4) | 2.2 (2.2–2.3) | 4.3 s (3.6 s–4.7 s) | 4.5 s (4.4 s–4.6 s) |
| Super | $0.0031 ($0.0029–$0.0033) | $0.0026 ($0.0025–$0.0028) | 2.3 (2.2–2.5) | 2.0 (2.0–2.1) | 11.9 s (10.6 s–12.7 s) | 10.8 s (10.3 s–11.5 s) |
| Ultra | $0.0135 ($0.0113–$0.0155) | $0.0128 ($0.0116–$0.0137) | 1.9 (1.7–2.2) | 1.9 (1.7–2.0) | 7.8 s (6.4 s–8.8 s) | 7.9 s (7.5 s–8.5 s) |

## Baselines on TEST (extraction + risk, no drafts)

Nano-only runs every task on Nano with no escalation; Ultra-for-everything runs every task on Ultra. The routed column excludes drafting cost so the three are comparable.

| Metric | Nano only | Routed (ours) | Ultra for everything |
|---|---|---|---|
| Classification: main category | 93.3% | 95.6% (93.3%–96.7%) | 100.0% |
| Field extraction accuracy | 90.6% | 91.9% (91.4%–92.6%) | 95.3% |
| Line-item accuracy | 90.6% | 88.7% (88.7%–88.7%) | 100.0% |
| Change detection: recall | 30.8% | 28.2% (23.1%–34.6%) | 30.8% |
| Change detection: precision | 53.3% | 63.1% (50.0%–70.0%) | 72.7% |
| High-risk flags: precision | 78.6% | 78.0% (76.9%–78.6%) | 75.0% |
| High-risk flags: recall | 68.8% | 66.7% (62.5%–68.8%) | 75.0% |
| Ultra calls per assessed email | 0.0 | 2.6 (2.3–2.8) | 4.7 |
| Cost per email (extraction + risk) | $0.0018 | $0.0131 ($0.0120–$0.0140) | $0.0155 |
| Latency per email | 34.0 s | 28.0 s (26.8 s–28.8 s) | 10.0 s |
| Emails that failed to process | 0 | 0 (0–0) | 0 |

## TEST per case (routed)

Field and line-item accuracy averaged over the runs; high-risk groups per run (expected → predicted).

| Case | Fields | Line items | Changes found | Expected high | Predicted high per run | Draft violations |
|---|---|---|---|---|---|---|
| test_001 | 100.0% | 100.0% | – | – | – / – / – | 0 |
| test_002 | 90.0% | 100.0% | 0/9 | value | – / – / – | 0 |
| test_003 | 100.0% | 100.0% | – | – | – / – / – | 0 |
| test_004 | 70.0% | – | 0/3 | schedule | – / – / – | 0 |
| test_005 | 100.0% | 100.0% | – | – | – / – / – | 0 |
| test_006 | 33.3% | 0.0% | – | – | – / – / – | 0 |
| test_007 | 90.0% | 100.0% | – | – | – / – / – | 0 |
| test_008 | 100.0% | 100.0% | – | – | – / – / – | 0 |
| test_009 | – | – | – | – | – / – / – | 0 |
| test_010 | – | – | – | – | – / – / – | 0 |
| test_011 | – | – | – | – | – / – / – | 0 |
| test_012 | 100.0% | 100.0% | 9/9 | schedule | schedule, value / schedule, value / schedule, value | 0 |
| test_013 | 100.0% | 100.0% | – | schedule | schedule / schedule / schedule | 0 |
| test_014 | 100.0% | 100.0% | – | – | schedule / schedule / schedule | 0 |
| test_015 | 90.0% | 0.0% | – | schedule | schedule / schedule / schedule | 0 |
| test_016 | 80.0% | – | 0/3 | – | – / – / – | 0 |
| test_017 | 92.6% | 100.0% | 2/6 | schedule, value | schedule, value / schedule / schedule, value | 0 |
| test_018 | 100.0% | 100.0% | – | – | – / – / – | 2 |
| test_019 | 100.0% | 100.0% | 6/6 | value | schedule, value / schedule, value / schedule, value | 0 |
| test_020 | 100.0% | 100.0% | – | – | – / – / – | 0 |
| test_021 | 80.0% | 100.0% | 0/9 | schedule | schedule / schedule / schedule | 0 |
| test_022 | 100.0% | 0.0% | – | schedule | schedule / schedule / schedule | 0 |
| test_023 | 100.0% | 100.0% | – | schedule | schedule / schedule / schedule | 0 |
| test_024 | 90.0% | 100.0% | – | – | – / – / – | 0 |
| test_025 | 81.5% | 100.0% | 0/12 | schedule, value | – / – / – | 0 |
| test_026 | 100.0% | 100.0% | – | – | – / – / – | 0 |
| test_027 | – | – | – | – | – / – / – | 0 |
| test_028 | 96.7% | 100.0% | – | – | – / – / – | 0 |
| test_029 | 100.0% | – | 5/6 | schedule | schedule / schedule / schedule | 0 |
| test_030 | 90.0% | 100.0% | 0/15 | schedule, value | schedule / schedule / schedule | 0 |

## How the sets were built

- **DEV (10 cases)** are the cases ExportAgent was built against; they are also the demo inbox. Prompts and policy may be changed using DEV only.
- **TEST (30 cases)** were written for this milestone and committed (commit `10e1b46`) before any run on them: 15 new fictional buyers in 12 countries and 7 currencies (EUR, GBP, USD, CAD, JPY, AUD, DKK); clean POs, revisions with attachments, revisions written only in the email body, reply threads, three-request emails, missing PO numbers and prices, a price contradicting the attached PO, size tables in six layouts (standard, sizes as rows, inline "S-200 / M-400", CSV, numeric sizes, Dutch with European number format), US-format and dd.mm.yyyy dates, feasible, tight and infeasible plans, and compliance-relevant products (kids' sleepwear for the US, a hood drawcord for the EU).
- **Labels** are hand-written: classification, every field, line items, review flags and expected changes. **Expected high risks** follow the severity rubric applied to the *true* order state in arrival order: *schedule* when the current plan is infeasible under the factory profile, *value* when the contract value changes by more than the threshold. That uses the same capacity model as the app, so this measures whether extraction, order matching and the agent get to the right finding, not whether the capacity model is right.
- Two dataset changes were made before any TEST run, both about realism, not results: the Desert Bloom order was cut from 40,000 to 3,000 pieces (one order should not saturate a 150-person factory and make every later order infeasible), and the Hudson & Pike tank order from 6,000 to 3,000.

## Changes made during this milestone

| When | Change | Found on |
|---|---|---|
| Before any TEST run | Planner prompt: read quoted messages from our own team; if anyone says fabric is in-house, run the feasibility check with `fabric_ready=true`. Policy: a fabric-ready check supersedes the pre-fetched one. | DEV case_007 (Ultra had stopped noticing "fabric is in-house" in the quoted thread) |
| Before any TEST run | Internal policy thresholds removed from drafting facts (Fix 2). | Milestone 6 review |
| After TEST runs | **None.** The failures below are reported, not fixed: fixing them now would tune the system to this TEST set. | – |

## What fails and why

1. **PO numbers copied with their revision suffix (test_002, test_017, test_021, test_030).** The extraction prompt says to copy identifiers "exactly as written", so the model returns "CL-7731 Revision A", "CPL-2044 (REV 2)", "MM-2290 rev 1". The revision does not match its order, a duplicate order is created, and the change is never diffed. It is also why the value changes in test_002 and test_030 are missed (the other two missed high-risk findings), and most of why change-detection recall is 28% on TEST against 100% on DEV, and Ultra-for-everything does no better (30.8%): it is a specification problem, not a model-size problem. It also has knock-on effects: the duplicate orders add phantom load to the capacity check, which is why test_014 (tight but feasible) and test_019 (feasible) get a false *schedule* high. Proposed fix: strip revision suffixes when matching orders, and say so in the prompt; then add DEV cases for it.
2. **Order reference put in the style field (test_004, test_016, test_025).** Body-only change emails ("we now need NR-55120 ex-factory 27/11") never say "PO", and Nano puts the reference in `style`. With no PO number nothing is matched, so the pulled-forward dates in test_004 and test_025, both infeasible, are not flagged: three of the roughly five high-risk findings missed per run. Proposed fix: fall back to matching known PO numbers anywhere in the email.
3. **An order without a PO number is classified as "no PO data" (test_006, every run).** "Our PO number will come from the new ERP next week" leads the classifier to say there is no order, so nothing is extracted. DEV case_010 is the same situation and passes; the TEST wording is enough to tip it.
4. **Review flags over-fire on body-only revisions (test_019, test_025, test_029).** The review rule requires every field for a `po_revision`, but a revision written in the email body only restates what changed; the rest carries over from the stored order. Those emails get five to seven "missing" flags each, which is why review precision is 8.5% on TEST. Proposed fix: for revisions, require only the PO number and the fields the email changes.
5. **Layout and language gaps.**
   - test_022: the size-table detector only recognises a header starting with "Colour", so a French "Coloris / Colour" table that Nano skipped never triggers escalation; its sizes are missing in all runs.
   - test_015: Nano shortens colour names ("Navy Stars" to "Navy").
   - test_018: the fact check reads the Dutch PO's "EUR 9,80" (decimal comma) as "EUR 9", a false violation in two of three runs.
   - test_012: the value threshold of 5,000 "in the order currency" calls a JPY 85,000 (about USD 570) price cut a high-value change. The label says it is not; this is a policy flaw.

## Reading the baselines

- **Ultra for everything is the most accurate** on TEST: field accuracy 95.3% against 91.9% routed, line items 100% against 88.7%. It costs $0.0155 per email against $0.0131 routed (extraction and risk, no drafts), about 18% more. Most of the routed setup's saving is small because Ultra's risk assessment dominates the cost either way. The accuracy gap, though, sits almost entirely in the cases above (shortened colour names, missed size tables, the no-PO classification), which better rules could fix without paying Ultra prices for extraction.
- **Nano only** is about 7× cheaper ($0.0018) and only about 1 pp behind routed on fields. It matches routed on high-risk flags because pre-fetch does the heavy lifting in Python. But it is the slowest at 34 s per email: as risk planner, Nano with thinking on writes long reasoning.
- **Latency is not like for like** in that table: routed includes drafting (about 10.8 s of Super time per email); without it routed is about 17 s per email. Ultra for everything is fastest (10 s) because it has no drafting and Ultra answers quickly with thinking off for extraction.
- Baselines ran once each; the routed min–max ranges show run-to-run differences of 1–3 pp on most metrics, so smaller gaps are not meaningful.

## Caveats

- The TEST emails and labels were written by the same assistant that built the system, so they may share its blind spots. Your manual check of the labels below is the guard against that.
- 30 cases: one case moves a percentage by about 3 points, and some metrics rest on few items (16 labelled high-risk findings, 26 labelled changes).
- "All intents" is scored as an exact set, and intent labels are partly a judgement call; DEV's 70% reflects that more than model error.

## TEST labels to verify by hand

These ten carry the trickiest judgement calls; please check them first.

| Case | What to check |
|---|---|
| test_004 | Reply thread: the new date is 27/11/2026 (pulled forward from 20/12/2026); expected *schedule* high. |
| test_006 | No PO number or price yet: labelled `new_po` with PO data; review fields po_number, unit_price, currency. |
| test_007 | Email says $3.40, attached PO says 3.60: label takes the PO (3.60) and expects unit_price to be flagged. |
| test_012 | JPY price cut: expected high is *schedule* only (the policy's value rule is overridden; see failure 5). |
| test_014 | Inline sizes; feasible but tight (90% of free capacity): no high risk expected. |
| test_017 | Colour added by email: expected changes (total 2,200 to 3,000, Forest added) and *schedule* + *value*. |
| test_019 | Colour cancelled by email: labelled `po_revision`; expected *value* high only (plan becomes tight, not infeasible). |
| test_022 | French size table; feasibility by capacity: expected *schedule* high. |
| test_025 | Partial update (one colour and the date): true total 4,500; expected changes and *schedule* + *value*. |
| test_029 | Price +3.9% (not high) and date pulled forward: expected *schedule* high only. |
