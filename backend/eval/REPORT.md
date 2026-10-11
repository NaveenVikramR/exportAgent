# ExportAgent evaluation report

DEV (21 cases) run 3× with the routed setup, end to end with the response cache off: classification and extraction, escalation, order matching and change detection, the risk agent, and drafts with the fact check. Values are mean (min–max) across runs. TEST v1 (30 cases) was run 1× after the fixes in this step. **TEST v1 is now seen**: its failures (Milestone 7) led to new DEV cases, and the fixes were made and checked on DEV only, but TEST v1 numbers below are no longer a held-out measurement. TEST v2 will be.

Model spend in the runs of this step: **$3.19** (including $0.41 for a DEV pass before the last fixes, kept in `runs/pre_fix/`, not in the tables).

## Results: routed setup

| Metric | DEV now | DEV at M7 (10 cases) | TEST v1 now (seen) | TEST v1 at M7 (held out) |
|---|---|---|---|---|
| Classification: main category | 93.7% (90.5%–100.0%) | 96.7% (90.0%–100.0%) | 96.7% | 95.6% (93.3%–96.7%) |
| Classification: all intents (exact set) | 84.1% (81.0%–85.7%) | 70.0% (60.0%–80.0%) | 96.7% | 92.2% (90.0%–93.3%) |
| Classification: has PO data | 100.0% (100.0%–100.0%) | 100.0% (100.0%–100.0%) | 100.0% | 94.4% (93.3%–96.7%) |
| Field extraction accuracy (after escalation) | 98.8% (98.5%–99.5%) | 97.8% (96.6%–98.9%) | 98.0% | 91.9% (91.4%–92.6%) |
| Line-item accuracy (colour, quantity, sizes) | 94.7% (90.9%–100.0%) | 88.9% (87.5%–91.7%) | 100.0% | 88.7% (88.7%–88.7%) |
| Human-review flags: recall | 100.0% (100.0%–100.0%) | 100.0% (100.0%–100.0%) | 83.3% | 33.3% (33.3%–33.3%) |
| Human-review flags: precision | 57.9% (50.0%–66.7%) | 100.0% (100.0%–100.0%) | 71.4% | 8.5% (8.3%–8.7%) |
| Order matching: email put on the right order | 100.0% (100.0%–100.0%) | n/a | 100.0% | n/a |
| Order matching: questions put to a person | 1.0 (1.0–1.0) | n/a | 0.0 | n/a |
| PO revision read from the PO number | 100.0% (100.0%–100.0%) | n/a | n/a | n/a |
| Change detection: recall | 98.0% (94.1%–100.0%) | 100.0% (100.0%–100.0%) | 92.3% | 28.2% (23.1%–34.6%) |
| Change detection: precision | 94.7% (84.2%–100.0%) | 100.0% (100.0%–100.0%) | 80.0% | 63.1% (50.0%–70.0%) |
| High-risk flags: precision | 100.0% (100.0%–100.0%) | 100.0% (100.0%–100.0%) | 100.0% | 78.0% (76.9%–78.6%) |
| High-risk flags: recall | 100.0% (100.0%–100.0%) | 100.0% (100.0%–100.0%) | 100.0% | 66.7% (62.5%–68.8%) |
| Drafts written | 41 (41–41) | 18 (18–18) | 56 | 52 (52–52) |
| Draft values fact-checked | 277 (263–285) | 129 (123–141) | 399 | 313 (299–327) |
| Draft fact-check violations | 0.3 (0.0–1.0) | 0.0 (0.0–0.0) | 1.0 | 0.7 (0.0–1.0) |
| Drafts with no violations | 99.2% (97.6%–100.0%) | 100.0% (100.0%–100.0%) | 98.2% | 98.7% (98.1%–100.0%) |
| Escalation rate (emails with an escalated field) | 36.7% (35.0%–40.0%) | 33.3% (33.3%–33.3%) | 34.6% | 23.3% (20.8%–25.0%) |
| Emails handled by Nano alone | 63.3% (60.0%–65.0%) | 66.7% (66.7%–66.7%) | 65.4% | 76.7% (75.0%–79.2%) |
| Escalations resolved by Super | 91.9% (85.7%–100.0%) | 100.0% (100.0%–100.0%) | 90.0% | 100.0% (100.0%–100.0%) |
| Escalation gain: field accuracy | +3.4 pp (+3.0 pp–+4.0 pp) | +3.0 pp (+2.2 pp–+3.4 pp) | +2.7 pp | +1.3 pp (+0.8 pp–+2.0 pp) |
| Escalation gain: line-item accuracy | +11.4 pp (+9.1 pp–+13.6 pp) | +12.5 pp (+12.5 pp–+12.5 pp) | +7.5 pp | +5.0 pp (+1.9 pp–+9.4 pp) |
| Ultra calls per assessed email | 2.3 (2.2–2.4) | 2.4 (2.1–2.8) | 2.8 | 2.6 (2.3–2.8) |
| Cost per email (all models) | $0.0188 ($0.0187–$0.0190) | $0.0169 ($0.0145–$0.0191) | $0.0212 | $0.0157 ($0.0144–$0.0165) |
| Latency per email (wall clock, end to end) | 31.6 s (29.1 s–35.4 s) | 24.2 s (20.8 s–25.9 s) | 32.1 s | 28.0 s (26.8 s–28.8 s) |
| Emails that failed to process | 0 (0–0) | 0 (0–0) | 0 | 0 (0–0) |

## Cost per email by pipeline stage (DEV, with drafts)

Extraction = classify, extract, escalated re-extraction and stated-change detection; risk = the agent's planning and reasoning; drafting = the reply and the internal note. Averaged over all DEV emails (emails without an order skip risk; emails needing no reply skip drafting).

| Stage | Routed (ours) | Nano only | Ultra for everything | Super for risk |
|---|---|---|---|---|
| Extraction | $0.0004 ($0.0004–$0.0005) | $0.0003 | $0.0038 | $0.0004 |
| Risk | $0.0151 ($0.0148–$0.0154) | $0.0020 | $0.0163 | $0.0036 |
| Drafting | $0.0034 ($0.0032–$0.0035) | $0.0013 | $0.0100 | $0.0031 |
| **Total** | $0.0188 ($0.0187–$0.0190) | $0.0036 | $0.0301 | $0.0071 |
| Model time, all stages | 29.9 s (28.0 s–32.4 s) | 82.5 s | 24.2 s | 31.0 s |

Quality of the same DEV passes:

| Metric | Routed (ours) | Nano only | Ultra for everything | Super for risk |
|---|---|---|---|---|
| Field extraction accuracy | 98.8% (98.5%–99.5%) | 96.0% | 99.0% | 99.0% |
| Line-item accuracy | 94.7% (90.9%–100.0%) | 81.8% | 100.0% | 93.2% |
| Change detection: recall | 98.0% (94.1%–100.0%) | 76.5% | 100.0% | 100.0% |
| High-risk flags: precision | 100.0% (100.0%–100.0%) | 100.0% | 100.0% | 100.0% |
| High-risk flags: recall | 100.0% (100.0%–100.0%) | 100.0% | 100.0% | 100.0% |
| Drafts with no violations | 99.2% (97.6%–100.0%) | 90.2% | 97.6% | 100.0% |

## Risk agent: Super instead of Ultra

Same pipeline, same pre-fetch and tools; only the planning and risk-reasoning calls move from Ultra to Super. One Super pass per split; the Ultra column is the routed passes of this step.

| Metric | DEV: Ultra | DEV: Super | TEST v1: Ultra | TEST v1: Super |
|---|---|---|---|---|
| High-risk flags: precision | 100.0% (100.0%–100.0%) | 100.0% | 100.0% | 100.0% |
| High-risk flags: recall | 100.0% (100.0%–100.0%) | 100.0% | 100.0% | 100.0% |
| High-risk flags: true / false positives / missed | 8/0/0 / 8/0/0 / 8/0/0 | 8/0/0 | 17/0/0 | 17/0/0 |
| Risk-stage calls per assessed email | 2.3 (2.2–2.4) | 2.4 | 2.8 | 2.3 |
| Risk-stage cost per assessed email | $0.0158 ($0.0156–$0.0161) | $0.0038 | $0.0205 | $0.0036 |
| Risk-stage model time per assessed email | 9.0 s (8.1 s–9.9 s) | 9.8 s | 12.3 s | 6.3 s |
| Emails assessed | 20 (20–20) | 20 | 26 | 26 |

## Cost and latency by model (routed, per email)

| Model | DEV cost | TEST v1 cost | DEV calls | TEST v1 calls | DEV model time | TEST v1 model time |
|---|---|---|---|---|---|---|
| Nano | $0.0003 ($0.0003–$0.0003) | $0.0003 | 2.4 (2.3–2.4) | 2.3 | 6.7 s (6.1 s–7.5 s) | 4.0 s |
| Super | $0.0035 ($0.0033–$0.0036) | $0.0032 | 2.5 (2.4–2.6) | 2.3 | 14.6 s (13.7 s–15.4 s) | 12.7 s |
| Ultra | $0.0151 ($0.0148–$0.0154) | $0.0177 | 2.2 (2.1–2.2) | 2.4 | 8.6 s (7.7 s–9.4 s) | 10.7 s |

## DEV per case (routed)

Field and line-item accuracy averaged over the runs; order matching and high-risk groups per run.

| Case | Fields | Line items | Right order | Changes found | Expected high | Predicted high per run | Draft violations |
|---|---|---|---|---|---|---|---|
| case_001 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_002 | 100.0% | 100.0% | yes / yes / yes | 9/9 | schedule, value | schedule, value / schedule, value / schedule, value | 0 |
| case_003 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_004 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_005 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_006 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_007 | 93.3% | – | yes / yes / yes | 3/3 | – | – / – / – | 0 |
| case_008 | – | – | – | – | – | – / – / – | 0 |
| case_009 | 100.0% | 100.0% | yes / yes / yes | 12/12 | schedule | schedule / schedule / schedule | 0 |
| case_010 | 100.0% | 33.3% | yes / yes / yes | – | schedule | schedule / schedule / schedule | 0 |
| case_011 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_012 | 100.0% | 100.0% | yes / yes / yes | 6/6 | value | value / value / value | 0 |
| case_013 | 100.0% | – | yes / yes / yes | 3/3 | schedule | schedule / schedule / schedule | 0 |
| case_014 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_015 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_016 | 90.0% | 100.0% | yes (asked) / yes (asked) / yes (asked) | 6/6 | value | value / value / value | 0 |
| case_017 | 100.0% | 66.7% | yes / yes / yes | 8/9 | schedule | schedule / schedule / schedule | 0 |
| case_018 | 96.7% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_019 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 1 |
| case_020 | 100.0% | 100.0% | yes / yes / yes | – | – | – / – / – | 0 |
| case_021 | 96.7% | 100.0% | yes / yes / yes | 3/3 | – | – / – / – | 0 |

## TEST v1 per case (routed, after the fixes)

Field and line-item accuracy averaged over the runs; order matching and high-risk groups per run.

| Case | Fields | Line items | Right order | Changes found | Expected high | Predicted high per run | Draft violations |
|---|---|---|---|---|---|---|---|
| test_001 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_002 | 100.0% | 100.0% | yes | 3/3 | value | value | 0 |
| test_003 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_004 | 90.0% | – | yes | 1/1 | schedule | schedule | 0 |
| test_005 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_006 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_007 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_008 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_009 | – | – | – | – | – | – | 0 |
| test_010 | – | – | – | – | – | – | 0 |
| test_011 | – | – | – | – | – | – | 0 |
| test_012 | 100.0% | 100.0% | yes | 3/3 | schedule | schedule | 0 |
| test_013 | 100.0% | 100.0% | yes | – | schedule | schedule | 0 |
| test_014 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_015 | 90.0% | 100.0% | yes | – | schedule | schedule | 0 |
| test_016 | 100.0% | – | yes | 1/1 | schedule | schedule | 0 |
| test_017 | 100.0% | 100.0% | yes | 2/2 | schedule, value | schedule, value | 0 |
| test_018 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_019 | 100.0% | 100.0% | yes | 1/2 | value | value | 0 |
| test_020 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_021 | 90.0% | 100.0% | yes | 3/3 | schedule | schedule | 1 |
| test_022 | 100.0% | 100.0% | yes | – | schedule | schedule | 0 |
| test_023 | 100.0% | 100.0% | yes | – | schedule | schedule | 0 |
| test_024 | 90.0% | 100.0% | yes | – | – | – | 0 |
| test_025 | 88.9% | 100.0% | yes | 3/4 | schedule, value | schedule, value | 0 |
| test_026 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_027 | – | – | – | – | – | – | 0 |
| test_028 | 100.0% | 100.0% | yes | – | – | – | 0 |
| test_029 | 100.0% | – | yes | 2/2 | schedule | schedule | 0 |
| test_030 | 100.0% | 100.0% | yes | 5/5 | schedule, value | schedule, value | 0 |

## How the sets were built

- **DEV (21 cases).**
  - case_001–010 are the cases ExportAgent was built against, and the demo inbox.
  - case_011–021 were added in this step, one or more for each failure pattern TEST v1 exposed. They are new emails with new fictional buyers (Tidewater Lane, Orchard Row, Brunnhof Sport, Marisma Moda, Hinoki Works), plus follow-ups to Maison Clairet (case_003) and Kestrel Kids (case_010). Nothing was copied from TEST.
  - Fixes are made and checked on DEV only.
- **TEST v1 (30 cases)** was held out until Milestone 7 (written and committed before any run, commit `10e1b46`). Its failures were analysed in the Milestone 7 report, so it is now **seen**. It is re-run here once to show the effect of the fixes, not as a held-out score.
- **TEST v2** will be written outside this codebase, from [TEST_V2_SPEC.md](TEST_V2_SPEC.md), and will be the next held-out measurement.
- **Labels** are hand-written: classification, every field, line items, review flags, the order each email belongs to, expected changes.
  - **Expected high risks** come from the severity rubric applied to the *true* order state in arrival order: *schedule* when the current plan is infeasible under the factory profile, *value* when the contract value changes by 10% or more, or by about USD 5,000.
  - They are now derived by [label_risk.py](label_risk.py) from the labels alone, never from app output.

## Changes in this step

Every change below was made against DEV cases. None was tuned on a TEST v1 email. TEST v1 failures from Milestone 7 only named the pattern; each fix was then written and checked against the new DEV case listed.

| # | Change | Kind | Pattern (from M7) | DEV case |
|---|---|---|---|---|
| 1 | PO numbers are split into a base and a revision: "TL-8812 Rev A", "-R2", "(REV 2)", "Amendment 1", "Revision 1". The base matches the order and the revision is stored with the version (`app/services/normalise.py`). | Python | Revision suffix kept in the PO number, so a duplicate order was created and changes never diffed | 012, 021 |
| 2 | Scored order matching (`app/services/order_matching.py`): same PO base +0.6 (a different PO number is a different order), PO number mentioned anywhere in the email +0.5, same style +0.3, different style −0.3, same buyer (legal suffixes ignored) +0.25, ex-factory within 45 days +0.15. A score of 0.6 or more is a match, below 0.35 a new order. | Python | Body-only emails name the order without "PO"; orders without a PO number | 013, 015, 016 |
| 3 | **Uncertain matches go to a person.** Scores from 0.35 to 0.6 store a question on the email. The Approvals page asks "Is this email about the existing order PO X from buyer Y?" with Yes/No (`GET /api/match-questions`, `POST /api/emails/{id}/match`). Nothing is recorded until someone answers, so no duplicate order is created. In the eval, the label answers. | Python + UI | Duplicate orders | 016 |
| 4 | Orders can exist without a PO number. The number is filled in when it arrives, and documents print it as TO BE CONFIRMED until then. An email classified as an order is always extracted, even if the classifier said "no PO data". | Python | Order without a PO number classified as "no PO data" | 014, 015 |
| 5 | **Field inheritance:** for an email about an existing order, a field the email does not restate is inherited from the order and not flagged "missing". It is listed under `inherited` on the extraction. | Python | Review flags over-firing on body-only revisions | 013, 016, 017 |
| 6 | Partial line-item updates: if the named colours add up to the stated total, it is the full list (a colour left out is removed); otherwise only the named colours change and the total is recomputed. A list of only colours the order does not have is an addition. | Python | Partial updates (TEST v1 test_019, test_025 pattern) | 016, 017 |
| 7 | The size-table detector accepts colour and size header words in English, French, Spanish, German, Dutch, Italian and Turkish, and sizes-as-rows tables. A detected table for which Nano returned no per-size quantities escalates the line items to Super. | Python | Non-English size table never escalated | 018, 019 |
| 8 | Colour names are restored from the email when Nano shortens them ("Ocean" → "Ocean Stripe"), matched by the same quantity next to the longer name. | Python | Shortened colour names | 011 |
| 9 | Decimal commas and dot or space thousands ("9,80", "1.500", "23.520,00", "1 500") parse in extraction and in the draft fact check. | Python | Decimal-comma price read as a different number | 017, 018, 019 |
| 10 | The value threshold is currency-aware: 10%, or about USD 5,000 converted with approximate rates in `policy/risk_policy.yaml`. A currency with no rate uses the percentage only. | Policy | JPY 85,000 (about USD 570) called a high-value change | 021 |
| 11 | *After the first DEV pass:* when the email gives no PO number but its "style" is the matched order's PO number, it is moved to the PO number. The matching score no longer penalises such a style as a different style (that comparison had used two different key formats, a bug). | Python | Order reference read as the style | 013 |
| 12 | *After the first DEV pass:* country short forms map to one name ("USA" → "United States", "UK" → "United Kingdom", …), so "UK" vs "United Kingdom" is no longer a change between versions. Buyer name variants ("TIDEWATER LANE" vs "Tidewater Lane Inc.") are not a change either. | Python | False changes between versions | 011–015 |

The only prompt edit: the planner's rubric line now says "about USD 5,000" instead of "5,000 in the order currency", to match change 10. The policy, not the prompt, enforces the severity. The first DEV pass with the new cases (before changes 11 and 12) is kept in `eval/runs/pre_fix/` and is not in the tables.

### Label changes

- **case_010** (DEV): expected high risk `[]` → `[schedule]`. Its order has no PO number, and such orders are now stored and assessed. With the other orders known by 28 Sep, the factory has no free capacity left before 18 Dec.
- **test_016** (TEST v1): `[]` → `[schedule]`, for the same reason. The order without a PO number in test_006 is a real booking and uses capacity; the M7 label left it out because the app could not store such orders. This is a correction of the label rule, applied to every case, not to a result.
- The risk labelling script moved from a scratch file into the repo ([label_risk.py](label_risk.py)). On DEV and TEST v1 it reproduces every committed label (after the two corrections above).

## Evaluation harness changes

- Change detection is now scored on the versions the order store actually recorded for each email, after matching. Before, an in-memory replay keyed by the raw PO number was used.
- Order matching is scored per email (right order: existing or new), with the questions put to a person counted. On TEST v1, whose labels have no `revises` key, the parent case is the earlier case with the same labelled PO number.
- Usage is recorded per stage (extraction, risk, drafting) and per model.
- New `super_risk` variant: risk planning and reasoning on Super instead of Ultra.
- The dataset loader reads JSON or YAML and a `test_v2` split.

### Fixed after the runs

| # | Change | DEV case |
|---|---|---|
| 13 | When a PO number arrives with no other change (case_015), no new version is written, so the latest version still had no PO number. A later email answered via the match question then got a false "PO number missing" flag (case_016, all three runs). The order's PO number is now part of the previous state used for inheritance. Covered by a unit test; the passes above predate it. Rerunning DEV 3× would cost about $1.20, against this step's $5 cap. | 016 |

## Reading the results

- **Order matching** put every email on the right order in all three DEV passes and on TEST v1: 20/20 DEV emails with order data per pass, 27/27 on TEST v1.
  - One question per DEV pass went to a person: case_016 ("add Heather Marl to the OR-SW-40 sweatshirts"), with buyer and style matching but no PO number or date, score 0.55.
  - TEST v1 needed no question.
  - Revision suffixes ("Rev A", "Revision 1") were read correctly in every pass.
- **Change detection on TEST v1** went from 28% to 92% recall, and precision from 63% to 80%. **High-risk flags** went from 78% / 67% to 100% / 100% (17 of 17, no false positive). These are the effects of changes 1, 2, 5 and 6. **TEST v1 is seen**, so read this as "the patterns found in M7 are fixed", not as a held-out score; TEST v2 is the next held-out measurement.
- **Review flags on TEST v1:** precision went from 8.5% to 71%, mostly from field inheritance (change 5). On DEV, precision is 58%. The false flags were:
  - case_016 `po_number`, 3 runs: fixed afterwards (change 13);
  - case_007, 2 of 3 runs: classified as a revision of an order that is not stored, so every field is required and there is nothing to inherit;
  - quantity-mismatch flags on case_010, 017 and 019, where Nano did misread a quantity, so the flag is arguably right and the label is strict.
- **DEV is harder than at M7.** The new cases cover the patterns that failed, so DEV and M7 numbers are not like for like. Line-item accuracy on DEV is 94.7%; the misses are Nano reading wrong colour quantities (case_010, case_017).

## Super instead of Ultra for the risk agent

- High-risk flags are identical:
  - DEV: 8 of 8 in every pass, no false positive.
  - TEST v1: 17 of 17 with Ultra and with Super.
- Super's risk stage costs about a quarter as much: $0.0038 against $0.0158 per assessed email on DEV, and $0.0036 against $0.0205 on TEST v1. Its model time is similar.
- The reason is the pre-fetch design. The schedule and value findings come from Python tools run before the model (feasibility, diff, value change), and the policy fixes severities after it. The model mainly decides which further checks to run and writes the summary.
- Ultra's extra reasoning does not change the high flags on these sets. It may still matter for the medium and low flags (compliance, buyer checks), which are not scored here.
- **Recommendation:** make Super the default for risk. That would bring the routed setup from about $0.019 to about $0.007 per email on DEV. One pass per split; confirm on TEST v2 before switching.

## Cost by stage

- Risk is the largest stage in the routed setup: about 80% of the cost per email. Extraction (Nano, plus Super for escalated fields) is about 2% and drafting (Super) about 18%.
- Ultra for everything costs 1.6× routed on DEV, mostly in drafting and extraction. It is the most accurate on line items (100%), but routed is within 1 pp on fields and level on risk.
- Nano only is the cheapest ($0.0036 per email) but the weakest:
  - line items 82%, change recall 77%, 90% of drafts with no fact-check violation;
  - the slowest, at 82 s of model time per email: Nano with thinking on writes long plans for the risk agent.

## What still fails (reported, not fixed)

On DEV (fixable on DEV in the next step):
- case_017: Nano reads Rouge as the order total (5,500 instead of 1,000), so the colour change is wrong. The quantity check flags it for review.
- case_010: Nano mixes up the colour quantities in an informal message.
- case_018: the German label "Artikel" is not read as the style.
- case_019: "confirm the ex-factory date" in a new Spanish PO is classified as a revision.

On TEST v1 (reported only; TEST v1 is seen but is still not used for fixes):
- test_019: a colour cancelled by email is recorded as a quantity change rather than a removal.
- test_025: a partial update's stated total is read as one colour's quantity.
- test_004, test_017 and test_021 show false changes from fields the email does not state:
  - test_004: a destination country inferred from the thread, and an item without a colour;
  - test_017: the destination country;
  - test_021: the style.
- test_007: the email-vs-attachment price contradiction is not flagged.
- test_026: the classification is wrong.

## Caveats

- DEV cases 011–021 and the TEST v1 labels were written by the same assistant that built the system. TEST v2, written outside the codebase, is the guard against shared blind spots.
- TEST v1 ran once after the fixes. The DEV min–max ranges show run-to-run variation of 1–5 pp on most metrics.
- Baselines (Nano only, Ultra for everything, Super for risk) ran once each.
- "All intents" is scored as an exact set, and intent labels are partly a judgement call.
