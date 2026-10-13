## How the sets were built

- **DEV (35 cases).** case_022–032 were added in the step after TEST v2, case_033–035 with the final two fixes (see below).
  - case_001–010 are the cases ExportAgent was built against, and the demo inbox.
  - case_011–021 were added in the previous step, one or more for each failure pattern TEST v1 exposed. They are new emails with new fictional buyers (Tidewater Lane, Orchard Row, Brunnhof Sport, Marisma Moda, Hinoki Works), plus follow-ups to Maison Clairet (case_003) and Kestrel Kids (case_010). Nothing was copied from TEST.
  - Fixes are made and checked on DEV only.
- **TEST v1 (30 cases)** was held out until Milestone 7 (written and committed before any run, commit `10e1b46`). Its failures were analysed in the Milestone 7 report, so it is now **seen**. It is re-run here once to show the effect of the fixes, not as a held-out score.
- **TEST v2 (30 cases)** was written by a separate assistant session from [TEST_V2_SPEC.md](TEST_V2_SPEC.md) alone, frozen in commit `24f19ae` before any run, and is the held-out measurement.
- **Labels** are hand-written: classification, every field, line items, review flags, the order each email belongs to, expected changes.
  - **Expected high risks** come from the severity rubric applied to the *true* order state in arrival order: *schedule* when the current plan is infeasible under the factory profile, *value* when the contract value changes by 10% or more, or by about USD 5,000.
  - They are now derived by [label_risk.py](label_risk.py) from the labels alone, never from app output.

## Final fixes before freezing the evaluation (DEV case_033–035)

Two fixes, each with a new DEV case. TEST v2 was not run again. The evaluation is frozen after this.

| # | Change | DEV cases |
|---|---|---|
| 22 | **A date that reads both ways never drives a high schedule finding.** The order version stores `date_unconfirmed` until an email states the date unambiguously. While it is set, the risk policy drops delivery and capacity findings drawn from the guessed date (they move to *Info checked*), adds one medium "Confirm ex-factory date with buyer" flag, and does not escalate to Ultra on the infeasible verdict. The reply asks the buyer to confirm the date, giving both readings, and offers no delivery options computed from the guess. A follow-up that does not restate the country is read with the order's country (found when DEV case_027 got a needless "confirm" flag on the first confirming pass). | 026, 032, 033 (027) |
| 23 | **A status email that mentions the order's current date is no change.** This holds even when the email writes the date without a year ("15/02") and the model reads it with another year or with day and month swapped. The update keeps the order's date, so no version and no change. Limitation: a genuine move to exactly the day/month swap of the current date ("from 03/04 to 04/03") cannot be told apart and would be missed. | 034, 035 (027) |
| 24 | The draft fact check reads year-first dates ("2027/04/23"), as Japanese POs write them (a false violation on case_031). | 031 |
| 25 | Scoring: `skip_fields` drops a field's value from scoring, but keeps its review flag when the label expects one. Only DEV case_026 and case_033 are affected (the value is unknowable, the flag is the point). | 026, 033 |

**Final DEV pass (35 cases, 1 run):**
- High-risk precision and recall are 100%: the case_026 and case_032 false positives are gone. case_026, case_032 and case_033 each get the one medium confirm flag, and their replies ask the buyer to confirm.
- case_027, case_034 and case_035 create no version and no change. case_035 was read as a date change and still changed nothing.
- 21% of risk runs went to Ultra. Risk cost per assessed email is $0.0064; cost per email $0.0094.
- The first confirming pass of these fixes (before the follow-up for case_027 and change 24) is kept in `runs/pre_fix/` and is not in the tables.

**Draft fact check:** one remaining false violation. The case_034 reply writes "15 February" for the buyer's "15/02", and the checker does not read a date without a year as the order's date. The other violation (case_023 internal note, "500 pcs") is a real catch.

## This step: Super-default risk routing and DEV-driven fixes (DEV case_022–032)

The held-out TEST v2 run showed the failure patterns listed under "TEST v2: what the held-out set shows" below. The fixes were specified from those patterns and written against **11 new DEV cases** (case_022–032). These have new fictional buyers (Pinecrest Supply, Haus Lindqvist, Wattle & Gum, Kumo Textiles, Northbay Outfitters), dates from 19 Oct to 2 Nov 2026, and no text from TEST v2. No TEST v2 file was changed. TEST v2 was re-run once afterwards and is reported as **seen**.

| # | Change | Kind | DEV cases |
|---|---|---|---|
| 14 | **Risk routing.** Super is the default for risk planning and reasoning. A run goes to Ultra when (a) the current plan is infeasible, so delivery options need weighing; (b) the email or thread says materials are already available ("fabric is in-house", "trims in stock") or offers a partial or split shipment; (c) Super's raw flags conflict with the Python feasibility result (a high delivery or capacity flag on a feasible or tight plan, or none on an infeasible one); or (d) Super's report fails validation even after the retry. Triggers (a) and (b) are checked before the run; (c) and (d) re-run the whole assessment on Ultra. The reason is a "routing" step in the trace, `result.routing` on the run, and the `detail` of every Ultra call in the LLM log (`app/agent/routing.py`). | Python | 007 (fabric in-house), 031 (partial shipment), every infeasible plan |
| 15 | **Ambiguous numeric dates.** When a date the model returned was written in the email as a numeric date whose day and month are both 12 or under (e.g. 03/04/2027), it is re-read with the email's convention. Evidence: dates in the same email that read only one way (10/19/2026, 20.10.2026), and the buyer's country (United States and Philippines month-first, Canada either, others day-first). Year-first and ISO dates are never touched. If the evidence is missing or contradictory, `delivery_date` is flagged `ambiguous_date` for review instead of guessed. The email's own stated old/new dates use the same convention. | Python | 022 (US), 023 (DE), 024 (AU), 025 (JP), 026 (CA, flagged) |
| 16 | **A repeated date is no change.** Quoted "earlier" values equal to the new ones no longer create a second version for a new order. For an existing order, an unchanged date already produced no version; this is now tested. | Python | 027 |
| 17 | **Revision-suffix normaliser.** Covers "Rev A", "rev. B", "REVISION 2", "Amendment 1", "Amendment No. 3", "Amdt 4", "R3", "(R3)", "v2", "_v2". A revision the model drops from the PO number is recovered from the text next to it. A PO with a revision read as the style becomes the PO. A bare letter ("WG-7781-A") is a revision only when the base PO is a known order and the full one is not. | Python | 028, 029, 031, 032 |
| 18 | **Colour changes.** Wording kept with a colour name is removed ("Nachtblau to" → "Nachtblau", "increase Navy" → "Navy"). "Drop / cancel / remove <colour>", "<colour> is cancelled" and "<colour> to 0" record the colour as removed (not when negated: "do not cancel"). | Python | 030 |
| 19 | **Classification enum.** The classify call sends the output JSON schema with the category enum, as `response_format` (checked live on Token Factory). Any category or intent outside the enum is mapped to "other", kept in `unrecognised`, flagged `unrecognised_intent`, and the email goes to review instead of failing. | Python + request schema | – (unit tests; no DEV email reproduces it) |
| 20 | **Eval oracle for match questions.** The label answers "yes" only if the question names the order the label links the email to; otherwise "no". It used to answer "yes" to any question on an email with a linked order. | Eval harness | 016 |

**Other changes:**
- The trace UI labels model steps Super or Ultra from the model actually used, and shows the routing step.
- The router takes an explicit per-call tier (`tier=`); a forced tier (the `nano_only` and `ultra_all` baselines) still wins.
- New eval variant `ultra_risk` (risk always on Ultra, no escalation), for the routing comparison.
- `super_risk` now means Super with escalation turned off.

**Runs and reporting:**
- Earlier runs were archived: the previous step's DEV and TEST v1 passes to `runs/before_routing/`, and the held-out TEST v2 passes to `runs/test_v2_heldout/`.
- The held-out TEST v2 section of this report is regenerated from those same files and is byte-for-byte unchanged.
- DEV labels: risk fields for case_022–032 were derived by `label_risk.py`; no existing label changed.

### Fixed after this step's runs

| # | Change | DEV case |
|---|---|---|
| 21 | Restoring a longer colour name from the email no longer re-attaches the wording after it. `restore_colour_names` turned the cleaned "Heather Charcoal" back into "Heather Charcoal to" (case_030, run 3), undoing change 18. Covered by a unit test; the passes above predate it. | 030 |

### Reading this step's results

**Risk routing (DEV, 3 runs):**
- 27% of risk runs went to Ultra: 25 runs over the three passes. 22 of them had an infeasible plan (in case_007 the thread also says the fabric is in-house); the other 3 were the partial-shipment offer in case_031, once per pass.
- The two after-the-run triggers, a conflict with feasibility and a failed validation, never fired on DEV or TEST v2.
- High-risk recall stayed at 100%. Precision is 89.7%, down from 100% before this step on the 21 earlier cases. The false positives come from case_026 and case_032 (2 of 3 runs each), see below.
- Risk cost per assessed email fell from $0.0158 (Ultra always, before this step) to $0.0093.
- The same DEV run with Ultra always on for risk (one pass, no drafts) scored 76.9% precision and 90.9% recall at $0.0189. On these cases, Ultra everywhere is not better than Super with escalation.

**What the new DEV cases show:**
- **Dates:** the US, German, Australian and Japanese dates (case_022–025) were read correctly in every run.
- **case_026 (Canadian date that reads both ways):** the model guessed 4 March in 2 of 3 runs. With that guess, the risk agent (on Ultra, since the plan looked infeasible) raised a *schedule* high on case_026 and its amendment case_032, against a label that expects none. **The ambiguity flag does not stop a guessed date from driving the risk assessment.** That is the next fix: when `delivery_date` is flagged ambiguous, assess feasibility for both readings or report the date as unknown.
  - The `ambiguous_date` review flag itself is not measured on case_026. The label puts `delivery_date` in `skip_fields`, which also drops it from the review metric; a label-design slip, noted rather than changed after the run.
- **Revision suffixes:** "REVISION 2", the bare "WG-7781-A", "Rev. 1" and "Amendment No. 1" were read in every run (PO revision accuracy 100%).
- **Colours (case_030):** the dropped Mustard Seed was recorded as removed in every run. Nano returned no line items for "Heather Charcoal to 900 pcs" in 2 of 3 runs (that change was missed), and the third run hit the bug fixed as change 21.
- **Repeated date (case_027):** classified correctly as a question in every run, so no order version was touched.

**TEST v2 after the fixes (seen, 1 run) against the held-out runs:**
- **Gains:**
  - PO revisions 100% (was 50%).
  - Change detection 85.0% / 63.0% (was 77.4% / 56.4%).
  - High-risk precision 87.5% (was 80.1%), recall still 100%.
  - No draft fact-check violations (was 1.7 per run).
  - No failed emails (t2_015's malformed intent no longer fails; change 19).
  - Cost per email $0.0095 (was $0.0215), with 18% of risk runs on Ultra.
- **Regressions on this single run, and their causes:**
  - **Intents (exact set) 63.3%, below the held-out range (73–76%).** Three new-PO emails (t2_003, t2_005, t2_007) were given extra intents (po_revision, delivery_change). This is the first run with the JSON schema in the request (change 19); DEV intents did not drop (85.4% vs 84.1%), so a single run cannot separate the schema from run-to-run variation. To watch.
  - **Line items 76.5%, below the held-out range (82–85%).** In t2_003 and t2_004, Nano's line items were right, but Super's escalated re-read (a size-total mismatch) returned colours without quantities. That is the escalation path, unchanged in this step, varying between runs.
  - **Review precision 35.7% (recall 83.3%).** Two emails (t2_006, t2_016) got the new `ambiguous_date` flag, which their labels do not expect. Whether those dates really read both ways from the email alone was not checked, to keep TEST v2 out of the fixing loop.
- **Unchanged:** the order question read as a date change (t2_022) still produces a false *schedule* high. No fix in this step addressed classification of such emails.

## Changes in the previous step (Milestone 7 patterns, DEV case_011–021)

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

### Fixed after the previous step's runs

| # | Change | DEV case |
|---|---|---|
| 13 | When a PO number arrives with no other change (case_015), no new version is written, so the latest version still had no PO number. A later email answered via the match question then got a false "PO number missing" flag (case_016, all three runs). The order's PO number is now part of the previous state used for inheritance. Covered by a unit test; the passes above predate it. Rerunning DEV 3× would cost about $1.20, against this step's $5 cap. | 016 |

## Reading the results

- **Order matching** put every email on the right order in all three DEV passes and on TEST v1: 20/20 DEV emails with order data per pass, 26/26 on TEST v1.
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

- DEV cases 011–021 and the TEST v1 labels were written by the same assistant that built the system. TEST v2, written by a separate session from the spec alone, is the guard against shared blind spots.
- TEST v1 ran once after the fixes. The DEV min–max ranges show run-to-run variation of 1–5 pp on most metrics.
- Baselines (Nano only, Ultra for everything, Super for risk) ran once each.
- "All intents" is scored as an exact set, and intent labels are partly a judgement call.

## TEST v2: what the held-out set shows

All 30 TEST v2 cases were written by a separate assistant session from TEST_V2_SPEC.md alone, and committed before any run. The build assistant checked only its structure: file pairs, schema, sums, and that the committed risk labels agree with `label_risk.py` (they all do). No code, prompt or label was changed after the results. Everything below is reported, not fixed.

**Headline.** On TEST v2, compared with TEST v1 after the fixes:
- Every expected high risk was found, in all three runs (recall 100%). Precision is lower (80%), because of the false positives below.
- Order matching was right in 98.7% of order emails.
- The weaker areas are change detection (77% recall, 56% precision), line items (83%), classification (88% main category) and review flags (45% precision, 72% recall).
- Some of this is variety DEV did not cover (see "What fails"), so it is the first honest measure of how the fixes generalise.

**What fails, by pattern (cases, runs out of 3):**

1. **Ambiguous numeric dates read the wrong way round** (t2_013, t2_016, t2_024; 3/3 each). For example, 12/02/2027 is read as 2 December instead of 12 February. Either the delivery date or the change on it is wrong, which accounts for most of the missed and unexpected `delivery_date` changes. The extraction has no rule for using the buyer's country or the other dates in the same email to settle the format.
2. **An order question read as a date change** (t2_022, 3/3). A status question that mentions dates is classified as `delivery_change` with PO data. The date then becomes a new version of the order, and the risk agent raises a *schedule* high on it in every run. That is one false high-risk flag per run; the others are t2_014 (*value*, 1 run) and t2_027 (*schedule*, in the run with the wrong match, pattern 7). Similarly, t2_019 and t2_030 (no order data) are said to carry PO data in all runs.
3. **Revision suffixes the splitter does not know** (t2_018 "Rev B", t2_024; 3/3). The revision is not read from the PO number: in t2_018 it lands in `style` or stays on the PO; in t2_024 it is missed. PO-revision accuracy is 50%.
4. **Colour-level change wording** (t2_010, t2_027; 3/3):
   - "Nachtblau to 1,600" yields a colour named "Nachtblau to".
   - A colour the label treats as removed is reported as a quantity change.
   - Both are the TEST v1 test_019 pattern, which was not covered by a DEV case.
5. **Style picks up extra text** (t2_017: "PK-TS-55 kids graphic tee", 3/3). A body-only follow-up also puts the PO number into `style` when the order has a different style (t2_014, t2_023, t2_025; 1–2/3). Change 11 only fixes this when the order is the one matched.
6. **One malformed classification reply** (t2_015). Nano returned an intent outside the allowed list twice, so the email failed in 1 of 3 routed runs and in the Super pass. The failure is visible, not silent, but nothing retries with a stronger model.
7. **Wrong match question answered "yes"** (t2_027, 1 of 3 runs). The question named a different order from the one the email was about, and the eval's label-oracle answered "yes" to it. In the app a person would see the PO and buyer named in the question and answer "no". This is a limitation of the oracle, but it also shows that a question naming the wrong order is possible.
8. **Review flags:**
   - `total_quantity` mismatch flags where the email's per-colour numbers do not add up the way the label reads them (t2_003, t2_008, t2_018).
   - Four extra flags on t2_015 (delivery date, Incoterm, port, total) in both runs where it was processed; not investigated, to keep TEST v2 unseen for fixes.
   - Flags the label expects but the system missed: `po_number` on t2_027 (3/3) and `unit_price` on t2_006 (2/3).

**Super instead of Ultra for risk, on TEST v2:** the same recall (100%) and fewer false positives (precision 85.7% vs 80.1%), at $0.0036 vs $0.0196 per assessed email. That is one Super pass against three Ultra passes, and t2_015 failed in the Super pass, so it had one fewer expected finding. Super's one false positive is t2_022, which Ultra also flags in every run: a misclassified email feeding the agent (pattern 2), not a reasoning error. This is now the third set where Super matches Ultra on high-risk findings.
