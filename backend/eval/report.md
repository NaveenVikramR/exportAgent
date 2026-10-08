# ExportAgent evaluation report

- Generated: 2026-10-08 15:12 UTC
- Cases scored: 10 (failed to run: 0)
- LLM mode: `live`

## Classification

| Metric | Result |
|---|---|
| Category | 9/10 (90%) |
| All intents (exact set) | 7/10 (70%) |
| Has PO data | 9/10 (90%) |

## Field extraction

| Field | Correct |
|---|---|
| buyer | 9/9 (100%) |
| po_number | 9/9 (100%) |
| style | 9/9 (100%) |
| currency | 8/9 (89%) |
| unit_price | 9/9 (100%) |
| total_quantity | 9/9 (100%) |
| delivery_date | 9/9 (100%) |
| incoterms | 8/9 (89%) |
| port | 9/9 (100%) |
| destination_country | 6/8 (75%) |
| **All fields** | **85/89 (96%)** |
| Line items (colour, quantity, sizes) | 19/24 (79%) |

## Human-review flags

| Metric | Result |
|---|---|
| Recall (fields that needed review and were flagged) | 7/7 (100%) |
| Precision (flagged fields that needed review) | 7/8 (88%) |

## Change detection

A change counts as correct when its field and both old and new values match the label.

| Metric | Result |
|---|---|
| Recall (labelled changes found) | 5/8 (62%) |
| Precision (reported changes that are correct) | 5/5 (100%) |
| case_009 | missed ['line_items.charcoal.sizes', 'line_items.dusty pink.sizes', 'line_items.sage.sizes'], unexpected - |

## Cost and latency

| Model | Tier | Source | Calls | Input tokens | Output tokens | Avg latency | Cost (USD) |
|---|---|---|---|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | nano | live | 24 | 20267 | 7135 | 2092 ms | 0.002928 |

Average cost per case: $0.000293

## Per case

| Case | Category | Intents | Fields | Line items | Review flags (expected / flagged) |
|---|---|---|---|---|---|
| case_001 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_002 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_003 | ok | wrong | 10/10 (100%) | 3/3 (100%) | - / - |
| case_004 | wrong | wrong | 8/9 (89%) | 3/3 (100%) | ['currency', 'delivery_date', 'incoterms', 'port', 'unit_price'] / ['currency', 'delivery_date', 'incoterms', 'port', 'unit_price'] |
| case_005 | ok | ok | 10/10 (100%) | 0/3 (0%) | - / - |
| case_006 | ok | ok | 9/10 (90%) | 3/3 (100%) | ['total_quantity'] / ['total_quantity'] |
| case_007 | ok | ok | 8/10 (80%) | n/a | - / ['incoterms'] |
| case_008 | ok | wrong | n/a | n/a | - / - |
| case_009 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_010 | ok | ok | 10/10 (100%) | 1/3 (33%) | ['po_number'] / ['po_number'] |
