# ExportAgent evaluation report

- Generated: 2026-10-06 17:58 UTC
- Cases scored: 10 (failed to run: 0)
- LLM mode: `mock`

> **Mock mode.** These numbers measure the rule-based stand-in in `app/llm/mock.py`, not a Nemotron model. They show that the pipeline and the scoring run end to end; they say nothing about model quality.

## Classification

| Metric | Result |
|---|---|
| Category | 9/10 (90%) |
| All intents (exact set) | 8/10 (80%) |
| Has PO data | 9/10 (90%) |

## Field extraction

| Field | Correct |
|---|---|
| buyer | 8/9 (89%) |
| po_number | 9/9 (100%) |
| style | 8/9 (89%) |
| currency | 8/9 (89%) |
| unit_price | 8/9 (89%) |
| total_quantity | 8/9 (89%) |
| delivery_date | 8/9 (89%) |
| incoterms | 8/9 (89%) |
| port | 8/9 (89%) |
| destination_country | 6/8 (75%) |
| **All fields** | **79/89 (89%)** |
| Line items (colour, quantity, sizes) | 15/24 (62%) |

## Human-review flags

| Metric | Result |
|---|---|
| Recall (fields that needed review and were flagged) | 5/7 (71%) |
| Precision (flagged fields that needed review) | 5/7 (71%) |

## Cost and latency

| Model | Tier | Source | Calls | Input tokens | Output tokens | Avg latency | Cost (USD) |
|---|---|---|---|---|---|---|---|
| `nvidia/nvidia-nemotron-3-nano-30b-a3b` | nano | mock | 18 | 12884 | 2595 | 2 ms | 0.000000 |

Average cost per case: $0.000000

## Per case

| Case | Category | Intents | Fields | Line items | Review flags (expected / flagged) |
|---|---|---|---|---|---|
| case_001 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_002 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_003 | ok | wrong | 9/10 (90%) | 0/3 (0%) | - / ['destination_country'] |
| case_004 | ok | ok | 9/9 (100%) | 0/3 (0%) | ['currency', 'delivery_date', 'incoterms', 'port', 'unit_price'] / ['currency', 'delivery_date', 'incoterms', 'port', 'unit_price'] |
| case_005 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_006 | ok | ok | 10/10 (100%) | 3/3 (100%) | ['total_quantity'] / - |
| case_007 | ok | ok | 10/10 (100%) | n/a | - / ['total_quantity'] |
| case_008 | ok | ok | n/a | n/a | - / - |
| case_009 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_010 | wrong | wrong | 1/10 (10%) | 0/3 (0%) | ['po_number'] / - |
