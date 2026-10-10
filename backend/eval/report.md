# ExportAgent evaluation report

- Generated: 2026-10-10 15:04 UTC
- Cases scored: 10 (failed to run: 0)
- LLM mode: `live`

## Classification

| Metric | Result |
|---|---|
| Category | 10/10 (100%) |
| All intents (exact set) | 8/10 (80%) |
| Has PO data | 10/10 (100%) |

## Field extraction

Nano extracts every field; fields that fail a Python check are re-extracted by Super (see Escalation).

| Field | Nano only | After escalation |
|---|---|---|
| buyer | 9/9 (100%) | 9/9 (100%) |
| po_number | 9/9 (100%) | 9/9 (100%) |
| style | 9/9 (100%) | 9/9 (100%) |
| currency | 8/9 (89%) | 9/9 (100%) |
| unit_price | 9/9 (100%) | 9/9 (100%) |
| total_quantity | 9/9 (100%) | 9/9 (100%) |
| delivery_date | 9/9 (100%) | 9/9 (100%) |
| incoterms | 8/9 (89%) | 9/9 (100%) |
| port | 9/9 (100%) | 9/9 (100%) |
| destination_country | 6/8 (75%) | 6/8 (75%) |
| **All fields** | **85/89 (96%)** | **87/89 (98%)** |
| Line items (colour, quantity, sizes) | 18/24 (75%) | 21/24 (88%) |

## Escalation (Nano → Super)

Triggers: size breakdown does not add up, a size table was present but not extracted, or the quoted source text is missing or does not state the value. Only the failing field is re-extracted, and Super's value is kept only if the same check then passes.

| Metric | Result |
|---|---|
| Emails handled by Nano alone | 6/9 (67%) |
| Escalation rate (emails with at least one escalated field) | 3/9 (33%) |
| Fields escalated | 3 |
| Resolved by Super (check passed, value kept) | 3/3 (100%) |
| Escalation cost | $0.0013 |

| Case | Field | Reason | Model | Outcome | Cost |
|---|---|---|---|---|---|
| case_004 | currency | source_quote_missing | `nvidia/nemotron-3-super-120b-a12b` | resolved | $0.0003 |
| case_005 | line_items | size_table_not_extracted | `nvidia/nemotron-3-super-120b-a12b` | resolved | $0.0006 |
| case_007 | incoterms | source_quote_missing | `nvidia/nemotron-3-super-120b-a12b` | resolved | $0.0003 |

## Human-review flags

| Metric | Result |
|---|---|
| Recall (fields that needed review and were flagged) | 7/7 (100%) |
| Precision (flagged fields that needed review) | 7/7 (100%) |

## Change detection

A change counts as correct when its field and both old and new values match the label.

| Metric | Result |
|---|---|
| Recall (labelled changes found) | 8/8 (100%) |
| Precision (reported changes that are correct) | 8/8 (100%) |

## Risk agent (Ultra)

Runs on every email linked to an order. With pre-fetch, Python looks up the order, diffs it and checks feasibility (and proposes delivery options) before the loop; Ultra keeps the optional tools and the final judgement. The flag policy then moves anything without specific evidence to *Info checked* and corrects severities to the rubric.

| Metric | Full loop (before) | Pre-fetch (after) |
|---|---|---|
| Emails assessed | 8 | 8 |
| Average Ultra calls per email | 4.1 | 2.2 |
| Average Ultra cost per email | $0.0210 | $0.0165 |
| Average tool rounds per email (cap 8) | 3.0 | 1.2 |
| High flags | 3 | 4 |
| Medium flags | 6 | 10 |
| Low flags | 1 | 2 |
| Info checked items | 25 | 33 |

Per case (Pre-fetch (after)):

| Case | Status | Rounds | Ultra calls | Ultra cost | Tools called (round 0 = pre-fetched) | Flags | Info |
|---|---|---|---|---|---|---|---|
| case_001 | completed | 1 | 2 | $0.0121 | find_order (0), check_delivery_feasibility (0), check_compliance, lookup_buyer | none | 3 |
| case_003 | completed | 1 | 2 | $0.0113 | find_order (0), check_delivery_feasibility (0), check_compliance, lookup_buyer | none | 4 |
| case_004 | completed | 2 | 3 | $0.0204 | find_order (0), check_compliance, lookup_buyer | **medium** data_quality | 3 |
| case_005 | completed | 2 | 3 | $0.0182 | find_order (0), check_delivery_feasibility (0), check_compliance, lookup_buyer | none | 4 |
| case_006 | completed | 1 | 2 | $0.0138 | find_order (0), check_delivery_feasibility (0), check_compliance | **medium** data_quality, **medium** compliance, **medium** compliance, **medium** compliance | 3 |
| case_002 | completed | 1 | 2 | $0.0169 | find_order (0), diff_po_versions (0), check_delivery_feasibility (0), check_delivery_feasibility (0), propose_delivery_options (0), lookup_buyer, check_compliance | **high** delivery, **high** price, **medium** delivery, **medium** quantity | 4 |
| case_007 | completed | 1 | 2 | $0.0219 | find_order (0), diff_po_versions (0), check_delivery_feasibility (0), check_delivery_feasibility (0), propose_delivery_options (0), check_compliance | **high** delivery, **medium** capacity, **medium** delivery, **low** delivery | 8 |
| case_009 | completed | 1 | 2 | $0.0173 | find_order (0), diff_po_versions (0), check_delivery_feasibility (0), propose_delivery_options (0), check_compliance, lookup_buyer | **high** delivery, **medium** price, **low** quantity | 4 |

## Drafts (Super) and fact check

Every date, quantity and price in a draft must appear in the order data, the tool results or the buyer's email; anything else is a violation shown to the reviewer.

| Metric | Result |
|---|---|
| Drafts written | 18 (10 replies, 8 internal notes) |
| Values checked | 132 |
| Fact-check violations | 0 |
| Drafts with no violations | 18/18 (100%) |
| Average drafting cost per email | $0.0026 |

| Case | Draft | Words | Values checked | Violations |
|---|---|---|---|---|
| case_001 | buyer_reply | 88 | 2 | none |
| case_001 | internal_note | 88 | 6 | none |
| case_003 | buyer_reply | 121 | 6 | none |
| case_003 | internal_note | 103 | 4 | none |
| case_004 | buyer_reply | 101 | 4 | none |
| case_004 | internal_note | 108 | 5 | none |
| case_005 | buyer_reply | 88 | 3 | none |
| case_005 | internal_note | 76 | 6 | none |
| case_006 | buyer_reply | 128 | 7 | none |
| case_006 | internal_note | 121 | 13 | none |
| case_002 | buyer_reply | 153 | 12 | none |
| case_002 | internal_note | 119 | 8 | none |
| case_007 | buyer_reply | 110 | 8 | none |
| case_007 | internal_note | 137 | 13 | none |
| case_008 | buyer_reply | 90 | 0 | none |
| case_009 | buyer_reply | 168 | 12 | none |
| case_009 | internal_note | 122 | 20 | none |
| case_010 | buyer_reply | 95 | 3 | none |

## Cost and latency (this run)

Source `cache` means the response was reused from an earlier identical request at no cost. For real cost and latency, run with `LLM_CACHE_ENABLED=false`. With `--agent`, the agent's Ultra calls and Super's escalation and drafting calls are included per agent pass; Nano's analysis calls in the agent passes are not repeated here.

| Pass | Model | Tier | Source | Calls | Input tokens | Output tokens | Avg latency | Cost (USD) |
|---|---|---|---|---|---|---|---|---|
| Scoring | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | nano | live | 22 | 18980 | 6737 | 1992 ms | 0.002756 |
| Scoring | `nvidia/nemotron-3-super-120b-a12b` | super | live | 3 | 3266 | 327 | 1697 ms | 0.001274 |
| Full loop (before) | `nvidia/Nemotron-3-Ultra-550b-a55b` | ultra | live | 33 | 117980 | 16658 | 2712 ms | 0.167954 |
| Full loop (before) | `nvidia/nemotron-3-super-120b-a12b` | super | live | 4 | 4345 | 349 | 1651 ms | 0.001618 |
| Pre-fetch (after) | `nvidia/Nemotron-3-Ultra-550b-a55b` | ultra | live | 18 | 68918 | 20991 | 4203 ms | 0.131891 |
| Pre-fetch (after) | `nvidia/nemotron-3-super-120b-a12b` | super | live | 25 | 36368 | 26303 | 5614 ms | 0.034583 |

Average cost per case: $0.034008

## Per case

| Case | Category | Intents | Fields | Line items | Review flags (expected / flagged) |
|---|---|---|---|---|---|
| case_001 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_002 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_003 | ok | wrong | 10/10 (100%) | 3/3 (100%) | - / - |
| case_004 | ok | ok | 9/9 (100%) | 3/3 (100%) | ['currency', 'delivery_date', 'incoterms', 'port', 'unit_price'] / ['currency', 'delivery_date', 'incoterms', 'port', 'unit_price'] |
| case_005 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_006 | ok | ok | 9/10 (90%) | 3/3 (100%) | ['total_quantity'] / ['total_quantity'] |
| case_007 | ok | ok | 9/10 (90%) | n/a | - / - |
| case_008 | ok | wrong | n/a | n/a | - / - |
| case_009 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_010 | ok | ok | 10/10 (100%) | 0/3 (0%) | ['po_number'] / ['po_number'] |
