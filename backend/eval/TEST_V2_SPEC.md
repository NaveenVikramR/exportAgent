# TEST v2: how to write cases

This is everything needed to write a held-out test set for ExportAgent without reading its code. Please do not share the cases with the people building the system until they have been run.

## 1. The domain in one page

**The factory.** Sri Velan Knits is a knitwear export factory in Tiruppur, India (about 150 people). It makes T-shirts, polos, sweatshirts, hoodies, leggings, rompers and similar knit garments. It ships FOB, CFR or CIF from the ports of **Tuticorin** or **Chennai**. Its merchandiser, **Karthik**, reads every buyer email; his colleagues (for example Suresh) sometimes forward emails to him.

**The buyers.** Fashion brands and retailers abroad email the factory. Typical emails:

- **New order**: a purchase order (PO) in the body or as an attachment. It has a PO number, style code, colours and quantities (often a size table), unit price and currency, Incoterm and port, ex-factory date, and destination.
- **Revision**: the same PO with changes. It can be a full new PO document ("PO 4471 Rev B", "Amendment 1") or a short email ("please cut Navy to 1,000 pcs"). A short email restates only what changes.
- **Delivery change**: only the ex-factory date moves, often deep in a reply thread with the old date quoted below.
- Others: questions about an order, sample or lab-dip approvals, requests for shipping documents, payment matters, and anything else.

One email can contain several requests.

**What ExportAgent does** with each email:
1. Classifies it.
2. Extracts the order fields.
3. Finds the order it belongs to. If unsure, it asks a person "Is this the same order?".
4. Records a new version and detects what changed.
5. Assesses risk.
6. Drafts a reply for a person to approve.

Your labels say what the right answer is for steps 1 to 5.

**What makes cases hard (please vary these):**
- PO numbers with revision suffixes.
- Order references that never use the word "PO".
- Orders with no PO number yet, with the number arriving in a later email.
- Body-only revisions.
- Partial updates that touch one colour.
- Contradictions between the email and its attachment.
- Reply threads with old values quoted.
- Size tables in different layouts (sizes as rows or as columns, inline "S-200 / M-400", CSV) and languages.
- Number formats ("9,80", "1.500", "1 500").
- Date formats (dd/mm, mm/dd, "5th March").
- Currencies, including ones with large unit values such as JPY.
- Colour names of several words.
- Forwarded emails.

**Rules for the content:**
- All buyers, people and companies must be fictional.
- Use `.example` email domains.
- Do not reuse buyers or PO numbers from `eval/dev` or `eval/test`.

## 2. Files and format

Put the files in `backend/eval/test_v2/`:

```
test_v2/cases/<id>.json       the email (input)
test_v2/expected/<id>.json    the label (answer)
```

- Use ids `t2_001`, `t2_002`, …
- JSON is shown below. YAML with the same structure also works; use `.yaml` files.
- The system never reads `expected/`.

### Case file (the email)

```json
{
  "id": "t2_007",
  "title": "One line describing what the case tests (not shown to the system)",
  "sender": "Name <name@buyer.example>",
  "subject": "Email subject",
  "received_at": "2026-11-04",
  "body": "The plain-text email body, including any quoted thread or forwarded header.",
  "attachments": [
    {
      "filename": "PO-4471.pdf",
      "content_type": "application/pdf",
      "text": "The attachment's text as a PDF-to-text tool would give it (keep the table layout with spaces or |)."
    }
  ]
}
```

- `received_at` sets the order in which emails are processed. Cases in one set are replayed in date order, then id order, into an empty order store.
- So a revision must come after its original, in the same set.
- Every set starts with an empty factory order book, so create any orders a revision needs earlier in the set.
- Give ex-factory dates about 6 to 20 weeks after `received_at`.

## 3. Label schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "classification", "extraction", "expected_review_fields"],
  "additionalProperties": false,
  "properties": {
    "id": {"type": "string"},
    "classification": {
      "type": "object",
      "required": ["category", "intents", "has_po_data"],
      "additionalProperties": false,
      "properties": {
        "category": {"$ref": "#/$defs/category"},
        "intents": {"type": "array", "items": {"$ref": "#/$defs/category"}, "minItems": 1},
        "has_po_data": {"type": "boolean"}
      }
    },
    "extraction": {
      "oneOf": [
        {"type": "null"},
        {
          "type": "object",
          "required": ["buyer", "po_number", "style", "currency", "unit_price", "total_quantity",
                       "delivery_date", "incoterms", "port", "destination_country", "line_items"],
          "additionalProperties": false,
          "properties": {
            "buyer": {"type": ["string", "null"]},
            "po_number": {"type": ["string", "null"]},
            "style": {"type": ["string", "null"]},
            "currency": {"type": ["string", "null"], "pattern": "^[A-Z]{3}$"},
            "unit_price": {"type": ["string", "null"], "pattern": "^[0-9]+(\\.[0-9]+)?$"},
            "total_quantity": {"type": ["integer", "null"]},
            "delivery_date": {"type": ["string", "null"], "format": "date"},
            "incoterms": {"type": ["string", "null"], "enum": ["FOB", "CFR", "CIF", "EXW", "FCA", "DAP", "DDP", null]},
            "port": {"type": ["string", "null"]},
            "destination_country": {"type": ["string", "null"]},
            "line_items": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["colour", "quantity"],
                "additionalProperties": false,
                "properties": {
                  "colour": {"type": "string"},
                  "quantity": {"type": "integer"},
                  "sizes": {"type": "object", "additionalProperties": {"type": "integer"}}
                }
              }
            }
          }
        }
      ]
    },
    "expected_review_fields": {"type": "array", "items": {"$ref": "#/$defs/field"}},
    "skip_fields": {"type": "array", "items": {"$ref": "#/$defs/field"}},
    "revises": {"type": "string"},
    "expected_po_revision": {"type": "string"},
    "expected_match_question": {"type": "boolean"},
    "expected_changes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["field", "old", "new"],
        "additionalProperties": false,
        "properties": {
          "field": {"type": "string"},
          "old": {"type": ["string", "integer", "object", "null"]},
          "new": {"type": ["string", "integer", "object", "null"]}
        }
      }
    },
    "partial_line_items": {"type": "boolean"},
    "true_state": {"type": "object"},
    "fabric_ready": {"type": "boolean"},
    "expected_high_risk": {"type": "array", "items": {"enum": ["schedule", "value"]}},
    "risk_note": {"type": "string"},
    "note": {"type": "string"}
  },
  "$defs": {
    "category": {"enum": ["new_po", "po_revision", "delivery_change", "order_query",
                          "sample_or_approval", "shipment_docs", "payment", "other"]},
    "field": {"enum": ["buyer", "po_number", "style", "currency", "unit_price", "total_quantity",
                       "delivery_date", "incoterms", "port", "destination_country"]}
  }
}
```

### What each key means

**`classification`**

- `category`: the main request.
  - `new_po`: a new order, including the formal PO for an order agreed earlier.
  - `po_revision`: any change to an existing order other than only its date.
  - `delivery_change`: only the ex-factory or delivery date changes.
  - `order_query`: a question about an order's status.
  - `sample_or_approval`: samples, lab dips, approvals.
  - `shipment_docs`: invoices, packing lists, B/L.
  - `payment`.
  - `other`.
- `intents`: every request in the email, including the main one.
- `has_po_data`: true when the email carries order data (a new order, a revision or a date change), even with no PO number. If it is false, `extraction` must be `null`.

**`extraction`**

These are the values the email and its attachments state. Use `null` for anything not stated. For a revision written in the body, the fields it does not restate are `null`.

- `buyer`: the buyer's company name as written, with its legal suffix ("Brunnhof Sport GmbH").
- `po_number`: the **base** PO number without any revision suffix. "TL-8812 Rev A" is `TL-8812`, and the suffix goes in `expected_po_revision`.
  - If the email names the order by its number without saying "PO", that number is still the PO number.
  - Use `null` if no number is known yet.
- `style`: the buyer's style or article code ("TL-HD-07"), not a description.
- `currency`: the ISO 4217 code. `unit_price` is a decimal string with a dot (EUR "9,80" is `"9.80"`; JPY 610 is `"610"`), price per piece.
- `total_quantity`: the order's total pieces, as stated or as the sum of the line items.
- `delivery_date`: the ex-factory or shipment date the buyer requires, in ISO format.
- `incoterms`: the code only. `port`: the named port or place only ("Chennai").
- `destination_country`: the English short name ("United States", "United Kingdom", "Germany").
- `line_items`: one entry per colour.
  - `colour`: the full name as written ("Ocean Stripe", not "Ocean"; keep the original language: "Tannengrün").
  - `quantity`: integer pieces.
  - `sizes`: only when per-size quantities are given; size label to pieces, adding up to `quantity`. Leave `sizes` out when only a ratio is given.
  - For a partial update that names only the colours that change, list just those and set `partial_line_items: true`.

**`expected_review_fields`**: the fields a person must check before acting.

- Every field missing from a `new_po`.
- The PO number when it is missing on any order email.
- Any value where the email and the attachment disagree; label the value the attachment states, and list the field.
- For a revision or date change, do **not** list fields the email simply does not restate. They carry over from the order.

**`skip_fields`**: fields not to score because the right answer is debatable (for example a buyer only identifiable from the email domain).

**Linking emails to orders**

- `revises`: the id of an earlier case about the **same order**.
  - It is required when the PO number alone does not link them: no PO number, a different reference, or the PO arriving later.
  - It is harmless otherwise.
  - Without it, cases with the same labelled `po_number` are the same order, and anything else is a new order.
- `expected_po_revision`: the revision suffix ("A", "2"), when the PO number carries one.
- `expected_match_question`: true if a careful person could not tell which order the email is about without asking, for example same buyer and style but no PO number and no date. This is informational.

**`expected_changes`**: for an email about an existing order, every change against the order as it stood before this email. Field names:

- `total_quantity`, `unit_price`, `currency`, `delivery_date`, `incoterms`, `port` (`old` and `new` in the label formats above).
- `line_items.<Colour>.quantity`, `line_items.<Colour>.unit_price`.
- `line_items.<Colour>.sizes`: only when the size **ratio** changes; values are the size maps.
- `line_items.<Colour>`: a colour added (`old: null`, `new: quantity`) or removed (`old: quantity`, `new: null`).

A PO number arriving for an order booked without one is not a change. Use `[]` when nothing changed.

**Risk**

- `true_state`: values of the true order that the email does not state, needed for the risk label. Example: `{"total_quantity": 2100}` after "add 300 pcs".
- `fabric_ready`: true if the thread says fabric is already in-house.
- `expected_high_risk`: optional. If you leave it out, `python -m eval.label_risk --split test_v2 --write` derives it from your labels (never from the system's output) with the rubric below. If you write it yourself, the tool prints any disagreement.

## 4. The risk rubric

A case expects a **high** risk in two groups:

- **schedule**: the order's current plan is infeasible.
  - The factory has 4,000 pcs/week of free sewing capacity: 10,000 pcs/week, 60% already booked outside the system.
  - Fabric takes 42 days from the email's date before sewing can start, unless `fabric_ready`.
  - The plan is infeasible when that leaves under 10 production days, or when the order plus the other orders in this set due between the email's date and this order's ex-factory date need more than the free capacity in that window.
- **value**: the contract value (unit price × total quantity) changed by 10% or more, or by about USD 5,000 or more. Other currencies are converted at the rates in `backend/policy/risk_policy.yaml`, so JPY 60,000 is about USD 400.

A plan that is merely tight, a small price change, or a compliance or buyer question are not "high" in this rubric.

## 5. Example: a revision

`test_v2/cases/t2_002.json`:

```json
{
  "id": "t2_002",
  "title": "Revision with a suffix in the PO number; one colour up",
  "sender": "Ana Ruiz <ana.ruiz@solmar-kids.example>",
  "subject": "SK-3307 rev 2",
  "received_at": "2026-11-10",
  "body": "Hi Karthik,\n\nAttached is SK-3307 rev 2: we need 400 more Coral Reef. Nothing else changes.\n\nAna\nSolmar Kids S.L.",
  "attachments": [{
    "filename": "SK-3307_rev2.pdf",
    "content_type": "application/pdf",
    "text": "SOLMAR KIDS S.L.\nPEDIDO / PO: SK-3307 rev 2\nStyle: SK-RM-12 baby romper\nPrice: EUR 4,10\nFOB Chennai\nEx-factory: 15/01/2027\nShip to: Málaga, Spain\n\nColour       0-3M  3-6M  6-12M  Total\nCoral Reef   300   600   300    1200\nSea Mist     200   300   300    800\n\nTotal: 2.000 pcs"
  }]
}
```

`test_v2/expected/t2_002.json` (the original order, `t2_001`, had Coral Reef 800 pcs as 200 / 400 / 200, Sea Mist as below, and a total of 1,600):

```json
{
  "id": "t2_002",
  "classification": {"category": "po_revision", "intents": ["po_revision"], "has_po_data": true},
  "extraction": {
    "buyer": "Solmar Kids S.L.",
    "po_number": "SK-3307",
    "style": "SK-RM-12",
    "currency": "EUR",
    "unit_price": "4.10",
    "total_quantity": 2000,
    "delivery_date": "2027-01-15",
    "incoterms": "FOB",
    "port": "Chennai",
    "destination_country": "Spain",
    "line_items": [
      {"colour": "Coral Reef", "quantity": 1200, "sizes": {"0-3M": 300, "3-6M": 600, "6-12M": 300}},
      {"colour": "Sea Mist", "quantity": 800, "sizes": {"0-3M": 200, "3-6M": 300, "6-12M": 300}}
    ]
  },
  "expected_review_fields": [],
  "revises": "t2_001",
  "expected_po_revision": "2",
  "expected_changes": [
    {"field": "total_quantity", "old": 1600, "new": 2000},
    {"field": "line_items.Coral Reef.quantity", "old": 800, "new": 1200}
  ],
  "expected_high_risk": ["value"],
  "note": "Value +25% (EUR 1,640): high by the percentage rule. Coral Reef keeps its 1:2:1 size ratio, so there is no sizes change."
}
```

## 6. Suggested mix for about 30 cases

- About 10 new orders, varying layout, language, currency and number format, including one or two with no PO number yet.
- About 10 revisions or date changes of those orders, some as full PO documents, some written only in the body, at least two with partial colour updates, and at least one where the PO number arrives later.
- About 5 emails with no order data: queries, samples, documents, payment.
- About 5 mixed emails with two or three requests.
- Across the set:
  - plans that are comfortably feasible, tight and infeasible;
  - value changes on both sides of the threshold, at least one in a currency other than USD.

Check each label file against the schema above before sending (any JSON Schema validator will do). We then run `pytest tests/test_eval_dataset.py`, which checks that line items add up and that the dates and prices parse.
