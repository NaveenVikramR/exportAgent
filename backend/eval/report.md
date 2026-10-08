# ExportAgent evaluation report

- Generated: 2026-10-08 20:52 UTC
- Cases scored: 10 (failed to run: 0)
- LLM mode: `live`

## Classification

| Metric | Result |
|---|---|
| Category | 10/10 (100%) |
| All intents (exact set) | 8/10 (80%) |
| Has PO data | 9/10 (90%) |

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
| Line items (colour, quantity, sizes) | 18/24 (75%) | 24/24 (100%) |

## Escalation (Nano → Super)

Triggers: size breakdown does not add up, a size table was present but not extracted, or the quoted source text is missing or does not state the value. Only the failing field is re-extracted, and Super's value is kept only if the same check then passes.

| Metric | Result |
|---|---|
| Emails handled by Nano alone | 6/10 (60%) |
| Escalation rate (emails with at least one escalated field) | 4/10 (40%) |
| Fields escalated | 4 |
| Resolved by Super (check passed, value kept) | 4/4 (100%) |
| Escalation cost | $0.0017 |

| Case | Field | Reason | Model | Outcome | Cost |
|---|---|---|---|---|---|
| case_004 | currency | source_quote_missing | `nvidia/nemotron-3-super-120b-a12b` | resolved | $0.0003 |
| case_005 | line_items | size_table_not_extracted | `nvidia/nemotron-3-super-120b-a12b` | resolved | $0.0006 |
| case_007 | incoterms | source_quote_missing | `nvidia/nemotron-3-super-120b-a12b` | resolved | $0.0003 |
| case_010 | line_items | size_total_mismatch | `nvidia/nemotron-3-super-120b-a12b` | resolved | $0.0004 |

## Human-review flags

| Metric | Result |
|---|---|
| Recall (fields that needed review and were flagged) | 7/7 (100%) |
| Precision (flagged fields that needed review) | 7/8 (88%) |

## Change detection

A change counts as correct when its field and both old and new values match the label.

| Metric | Result |
|---|---|
| Recall (labelled changes found) | 8/8 (100%) |
| Precision (reported changes that are correct) | 8/8 (100%) |

## Risk agent (Ultra)

Runs on every email linked to an order. Ultra plans and writes the report; tools do the maths.

| Metric | Result |
|---|---|
| Emails assessed | 8 |
| Average Ultra calls per email | 4.4 |
| Average Ultra cost per email | $0.0219 |
| Average tool rounds per email (cap 8) | 3.1 |
| Total agent cost | $0.1751 |

| Case | Status | Rounds | Ultra calls | Ultra cost | Tools called | Flags |
|---|---|---|---|---|---|---|
| case_001 | completed | 2 | 3 | $0.0128 | find_order, check_delivery_feasibility, check_compliance, lookup_buyer | **medium** compliance, **low** buyer, **low** delivery |
| case_003 | completed | 2 | 3 | $0.0129 | find_order, check_delivery_feasibility, check_compliance, lookup_buyer | **medium** compliance, **medium** buyer, **low** delivery |
| case_004 | completed | 2 | 3 | $0.0139 | find_order, check_compliance, lookup_buyer | **medium** delivery, **medium** price, **medium** compliance, **low** buyer, **low** data_quality |
| case_005 | completed | 2 | 3 | $0.0155 | find_order, check_delivery_feasibility, check_compliance, lookup_buyer | **medium** buyer, **medium** compliance, **low** data_quality |
| case_006 | completed | 2 | 3 | $0.0149 | find_order, check_delivery_feasibility, check_compliance | **medium** compliance |
| case_002 | completed | 6 | 8 | $0.0434 | find_order, diff_po_versions, check_delivery_feasibility, check_delivery_feasibility, check_compliance, lookup_buyer, lookup_buyer | **high** delivery, **high** capacity, **medium** quantity, **medium** compliance, **low** buyer |
| case_007 | completed | 5 | 6 | $0.0263 | find_order, diff_po_versions, check_delivery_feasibility, check_delivery_feasibility, check_compliance | **medium** delivery, **low** compliance |
| case_009 | completed | 4 | 6 | $0.0353 | find_order, diff_po_versions, check_compliance, lookup_buyer, check_delivery_feasibility | **high** capacity, **high** delivery, **medium** price, **low** data_quality |

## Cost and latency (this run)

Source `cache` means the response was reused from an earlier identical request at no cost. For real cost and latency, run with `LLM_CACHE_ENABLED=false`. With `--agent`, the risk agent's Ultra calls are included.

| Model | Tier | Source | Calls | Input tokens | Output tokens | Avg latency | Cost (USD) |
|---|---|---|---|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | nano | live | 23 | 19803 | 7144 | 1478 ms | 0.002903 |
| `nvidia/nemotron-3-super-120b-a12b` | super | live | 4 | 4337 | 407 | 1053 ms | 0.001667 |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | ultra | live | 35 | 124642 | 16817 | 2192 ms | 0.175093 |

Average cost per case: $0.017966

## Per case

| Case | Category | Intents | Fields | Line items | Review flags (expected / flagged) |
|---|---|---|---|---|---|
| case_001 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_002 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_003 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_004 | ok | wrong | 9/9 (100%) | 3/3 (100%) | ['currency', 'delivery_date', 'incoterms', 'port', 'unit_price'] / ['currency', 'delivery_date', 'incoterms', 'port', 'unit_price'] |
| case_005 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_006 | ok | ok | 9/10 (90%) | 3/3 (100%) | ['total_quantity'] / ['total_quantity'] |
| case_007 | ok | ok | 9/10 (90%) | n/a | - / - |
| case_008 | ok | wrong | n/a | n/a | - / - |
| case_009 | ok | ok | 10/10 (100%) | 3/3 (100%) | - / - |
| case_010 | ok | ok | 10/10 (100%) | 3/3 (100%) | ['po_number'] / ['po_number', 'total_quantity'] |
