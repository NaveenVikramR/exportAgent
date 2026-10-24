# Scenario test on the live site: six buyer emails

**When:** 24 October 2026, 19:10–19:18 UTC, on <https://3-104-80-176.sslip.io>.
**How:** `run_scenarios.py` pasted each email into **Try your own email** with Playwright and Chromium, in order (T1 → T6). After each one, it waited until the page had finished the analysis, the risk step and the drafts. It then saved full-page screenshots and the API's view of the result to `results/T*.json`. Nothing was fixed or re-run during the test.
**Starting state:** the clean demo (8 emails, 6 orders), from `results/state_before.json`.
**Cost of the test:** **$0.1226** of live model calls. Today's spend went from $0.0542 to $0.1768 of the $1.00 cap.
**After the test:** the demo was reset and checked: 8 emails, the 6 demo orders, and no test orders. Today's spend stayed at $0.1768; resetting does not reset the cap.

## Summary

| | Expected | Result | Mismatches |
|---|---|---|---|
| **T1** new PO | all fields, no high risk | All 10 fields and both colours correct. **High delivery flag** | 1: false high. The cause is the capacity check (see A) |
| **T2** Rev A | matched, Rev A, +600, 10 Dec, high schedule + value, Ultra, options | Matched, Rev A, +600, pulled forward to 10 Dec, high delivery + high value (+20%), Ultra | 3: the reply offers one option, not a choice; style read as the PO number, giving a false style change; extra "new PO" intent |
| **T3** fabric in-house | 18 Dec, fabric used, no false high | Date moved to 18 Dec, Ultra re-ran feasibility with `fabric_ready=true`. **Still high** | 1: the high stands, but given the demo order book it is arguably correct (see A) |
| **T4** ambiguous date | medium "confirm date", reply asks | Read as **2 March 2027** with no flag; reply repeats "03/02/2027" | 3: no ambiguity detected; destination "United States" invented; classified as a PO revision |
| **T5** German PO | 11.90, 1,400, German colours, unit_price flagged | 11.90, 1,400, Waldgrün and Anthrazit all correct | 1: the 11,40 (text) vs 11,90 (table) price conflict was **not** flagged |
| **T6** multi-intent | all three points, no new version | Lab dips, payment and PP samples all answered; no new version | 0 (minor: extra "new PO" intent) |

**Model use:**
- **Risk on Ultra:** T1, T2, T3 and T6, each because the current plan came out infeasible (in T3 also because the thread says fabric is in-house). T4 and T5 stayed on Super.
- **Escalated extraction to Super:** T2 (1 field), T3 (5 fields), T6 (1 field).
- **Fact check:** all 12 drafts passed with 0 violations.

## Findings across scenarios (reported, not fixed)

**A. The capacity check counts other orders against too short a window (likely bug). This causes T1's false high.**
`check_feasibility` compares two numbers:
- the capacity left **after** the fabric lead time (as of + 42 days, up to the delivery date);
- the **whole** quantity of every other order due before the delivery date.

Orders due early, such as NW-45098 on 10 Nov (9,000 pcs) or BP-778455 on 20 Nov, are produced while this order's fabric is still on its way, so they shouldn't use up this order's window. For T1, the window held 31,428 pcs, against 39,900 pcs of other orders plus 3,000 → "0 pcs free, 136.5%, slack −21 days". Counted over the whole period from 24 Oct, the factory has about 55,400 pcs of free capacity. That against 42,900 is about 77%, which is feasible.

T3 is different. 33,900 pcs of other orders are due by 18 Dec against about 31,400 pcs of capacity from today, so even with fabric in-house the plan really is short. The flag there is defensible, and it's the demo's order book that is full.

**B. Ambiguous dates are settled by an invented destination (T4).** The email gives no destination, only FOB Chennai, yet extraction set `destination_country = "United States"` (confidence 0.9). Read with the US convention, "03/02/2027" becomes 2 March, so no date-confirmation flag was raised. The reply then repeats "03/02/2027" back to the buyer, which is still ambiguous.

**C. A price contradiction inside one email is not caught (T5).** The text says "EUR 11,40 as agreed on the phone" and the table says "EUR 11,90 / Stück". Extraction took 11.90 at confidence 1.0, with no review flag, and the reply confirms 11.90 without mentioning 11,40. The review rules check that a quote exists and that quantities add up, but not that two stated prices agree. The same pattern was missed on TEST v1 (test_007).

**D. Style is read as the PO number when the email names no style (T2, T3, T6).** T2 extracted `style = "HLA-24019"`. That recorded a false *style HL-TS-310 → HLA-24019* change in version 2, and the order's style now shows the PO number. This is TEST v2's pattern 5.

**E. Spurious intents.** T2 was classified with `new_po` as well as revision and delivery change, and the reply opens "I acknowledge your requests for a new PO, PO revision, and delivery change". T4 was classified `po_revision` instead of `new_po`, and its reply opens "I acknowledge your request for a PO revision". T6 also carries `new_po`.

**F. Replies offer a single option when there is no split.** In T2 and T3, `propose_delivery_options` found no partial shipment that ships on time, so the replies offer one date (24 Feb 2027) and say no split is available. That is consistent with the evidence, but it is one proposal rather than "options".

**G. Tavily sources are only visible as raw JSON in the trace,** not as links on the risk card. This is fix 2. The buyer lookups returned mostly unrelated pages (law-firm news, prnewswire, YouTube), and the findings correctly say "no adverse information".

## Scenario details

Screenshots: `screenshots/T*_email.png`, the full email page, and `T*_order.png`, the order with its versions. Also `00_dashboard_before.png` and `99_dashboard_after.png`. Raw results: `results/T*.json`.

### T1: New PO HLA-24019 (56 s, $0.0247, 7 calls)
- **Classification:** `new_po` (0.99).
- **Fields:** buyer Harbourline Apparel Inc., PO HLA-24019, style HL-TS-310, USD 4.20, 3,000 pcs, ex-factory 2027-01-29, FOB Tuticorin, United States. Line items Deep Navy 1,800 and Stone Grey 1,200, with sizes. No review flags.
- **Order:** new order 7, version 1. No match question.
- **Risk** (Ultra, escalated because the current plan is infeasible):
  - **HIGH delivery:** 3,000 pcs short, 136.5%, slack −21 days, earliest full date 2027-02-23 (E2, E3).
  - MEDIUM data quality: no fibre composition for US labelling (E1, E5).
  - Info: buyer (nothing adverse), US labelling rules, delivery options.
- **Tavily:** compliance from eurofins.com, wunderlabel.com, compliancegate.com and collectivestudioltd.com; buyer from archerlaw.com, prnewswire.com, naumd.com and cozen.com.
- **Reply:** confirms the details and says 29 Jan is not feasible, offering 23 Feb 2027. Fact check passed (5 values; the internal note 10).
- ❌ Expected no high risk; got a high delivery flag (finding A).

### T2: HLA-24019 Rev A (50 s, $0.0262, 9 calls)
- **Classification:** `po_revision`, with intents `new_po`, `po_revision` and `delivery_change` (0.96).
- **Fields:** "HLA-24019 Rev A" read as PO HLA-24019, revision A. 3,600 pcs, 2026-12-10, Deep Navy 2,400. Currency, price, Incoterm and port inherited from v1.
- **Order:** matched to order 7, which became version 2 (rev A). No match question. Changes:
  - total 3,000 → 3,600;
  - delivery 2027-01-29 → 2026-12-10, *delivery pulled forward*;
  - Deep Navy 1,800 → 2,400;
  - style HL-TS-310 → HLA-24019 (false).
- **Risk** (Ultra, escalated because the plan is infeasible):
  - **HIGH delivery:** 5 production days after the 42-day fabric lead time, 3,600 pcs short.
  - **HIGH price:** contract value +20% (USD 12,600 → 15,120).
- **Tavily:** compliance from peach-labels.com, politedraft.com, greenwich-mercantile.com and regenerate-trade.com.
- **Reply:** 10 Dec is not feasible; the earliest full date is 24 Feb 2027, with "no partial-shipment option". Fact check passed (4 values; the note 12).
- ✅ Matched, Rev A, +600 pcs, pulled forward to 10 Dec, high schedule and value, Ultra.
- ❌ The reply proposes one date, not a choice (F). The style was read as the PO number, giving a false style change (D). Extra `new_po` intent, echoed in the reply (E).

### T3: Fabric in-house, 18 Dec (59 s, $0.0281, 13 calls)
- **Classification:** `delivery_change` (0.96).
- **Fields:** delivery 2026-12-18. PO inherited from the thread, after 5 fields were escalated to Super.
- **Order:** order 7 became version 3; the only change is delivery 2026-12-10 → 2026-12-18.
- **Risk** (Ultra, escalated for two reasons: the plan is infeasible, and *the thread says materials are available ('fabric is in-house')*):
  - Ultra re-ran `check_delivery_feasibility` with `fabric_ready=true`.
  - **HIGH delivery:** infeasible even with fabric in-house: 3,600 pcs short, 66 production days needed against 55 available.
- **Reply:** thanks Emily for the fabric news and says 18 Dec can't be met even so. It explains the numbers, offers 24 Feb 2027 and says no split is feasible. Fact check passed.
- ✅ Changed to 18 Dec; the fabric-in-house what-if was used.
- ⚠️ Still high. Given the demo order book this is correct, not a false high (see A).

### T4: PO BK-7781, ambiguous date (46 s, $0.0073, 8 calls)
- **Classification:** `po_revision` (0.96). It should be `new_po`.
- **Fields:** Blue Kite Goods, BK-7781, BK-PL-02, USD 6.75, 1,500 pcs, **2027-03-02**, FOB Chennai, **United States (0.9; not in the email)**. Forest Green line items are correct. No review flags.
- **Order:** new order 8, version 1.
- **Risk** (Super, no escalation): MEDIUM delivery, tight: 95% of free capacity, 4 days of slack.
- **Tavily:**
  - compliance from eurofins.com, tradeaiders.com, collectivestudioltd.com and compliancegate.com;
  - buyer from economictimes, linkedin.com, flybluekite.com and cnbc.com.
- **Reply:** says the date "03/02/2027" is tight and "fabric is not yet ready", and asks for a revised date or a split. It does not ask which date was meant.
- ❌ No ambiguity detected, so no medium "confirm date" flag and no confirmation question (B). The destination was invented (B). Wrong category (E).

### T5: German PO NW-5520 (51 s, $0.0070, 7 calls)
- **Classification:** `new_po` (0.98).
- **Fields:** Nordwind Textil GmbH, NW-5520, NW-HD-14, EUR **11.90**, **1,400** pcs, 2027-02-26, FOB Chennai, Germany. Line items **Waldgrün** 600 (100/200/200/100) and **Anthrazit** 800 (150/250/250/150). **No review flags.**
- **Order:** new order 9.
- **Risk** (Super): MEDIUM delivery, 99.7% of free capacity, 0 days of slack. Info: German fibre labelling under EU Regulation 1007/2011.
- **Tavily:** compliance from surajmal.com, dpassion.co.in, tradeaiders.com and ftc.gov.
- **Reply:** lists quantity, colours, EUR 11.90, FOB Chennai and 26 Feb, notes the tight timeline and asks Anna to confirm. It does not mention 11,40.
- ✅ 11,90 → 11.90, 1.400 → 1,400, German colour names kept.
- ❌ `unit_price` not flagged for review despite 11,40 in the text (C).

### T6: Lab dips, payment, PP samples (66 s, $0.0294, 8 calls)
- **Classification:** `sample_or_approval`, with intents `sample_or_approval`, `payment` and `new_po` (0.96).
- **Order:** matched to order 7; **no new version** (still 3).
- **Risk** (Ultra, because the stored plan is infeasible):
  - HIGH delivery (the existing 18 Dec plan).
  - LOW: the Stone Grey lab dip was rejected and needs resubmitting.
  - Info: the 30% advance was paid.
- **Reply:** answers each point in a numbered list:
  1. Deep Navy option B approved; Stone Grey to be resubmitted.
  2. The 30% advance has been received.
  3. Two PP samples per colour in size M before cutting.

  It then adds the delivery position (earliest 24 Feb 2027). Fact check passed.
- ✅ Several intents recognised, no new version, all three points covered. Minor: an extra `new_po` intent (E).

## Cost and latency per email

| | End to end | Model calls | Cost | Risk model |
|---|---|---|---|---|
| T1 | 56.4 s | 7 | $0.0247 | Ultra |
| T2 | 49.7 s | 9 | $0.0262 | Ultra |
| T3 | 58.7 s | 13 | $0.0281 | Ultra |
| T4 | 46.0 s | 8 | $0.0073 | Super |
| T5 | 50.9 s | 7 | $0.0070 | Super |
| T6 | 65.8 s | 8 | $0.0294 | Ultra |
| **Total** | 5.5 min | 52 | **$0.1226** | |

These are above the $0.0094 per email measured on DEV, because finding A sent 4 of the 6 risk runs to Ultra. "End to end" runs from submitting the form to the page finishing, over a slow link from the test PC to Sydney.

## Files

- `run_scenarios.py`: the test runner. `summarise.py` prints the results.
- `scenarios.txt`: the six emails, exactly as sent.
- `results/`: `T1.json` … `T6.json`, `state_before.json` and `spend.json`.
- `screenshots/`: the email and order pages per scenario, and the dashboard before and after.
