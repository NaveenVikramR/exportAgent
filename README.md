# ExportAgent

An AI export desk for small and mid-size apparel and textile exporters. A buyer email arrives; ExportAgent classifies it, extracts the purchase order, detects what changed against the previous PO version, reasons about delivery and compliance risk, drafts a reply for a human to approve, and generates the Commercial Invoice and Packing List.

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps and Agents).

> Status: Milestone 5 of 8 (drafts and human-in-the-loop). Sections marked _to be filled_ are completed as the build progresses.

## How we use NVIDIA Nemotron + Nebius Token Factory

Every LLM call in ExportAgent is a runtime call to the Nebius Token Factory inference API, made with the OpenAI-compatible SDK from a single module, [backend/app/llm/router.py](backend/app/llm/router.py). Callers never name a model. They declare a task type, and the router picks the Nemotron tier from configuration.

| Task | Tier | Why |
|---|---|---|
| Email classification, field extraction, PO change detection | Nemotron Nano | Fast and cheap for high-volume structured work |
| Re-extracting a single field that failed a Python check (escalation) | Nemotron Super | Stronger model, only where Nano demonstrably failed |
| Drafting buyer replies and internal notes (thinking on) | Nemotron Super | Better writing quality at moderate cost |
| Risk reasoning and multi-step planning in the agent loop | Nemotron Ultra | Strongest reasoning, used sparingly |

**Escalation routing.** Nano extracts every field first. Plain-Python checks then look for three failures: a size breakdown that does not add up, a size table in the email that was not extracted, and a quoted source text that is missing from the email or does not state the value. Only the failing field is re-extracted by Super, and Super's value is kept only if the same check then passes. Every escalation is logged with field, reason, model and cost ([backend/app/services/escalation.py](backend/app/services/escalation.py)).

**The risk agent.** Ultra runs an observe → reason → act loop with OpenAI-style tool calling, a hard cap of 8 tool rounds, and `max_tokens` on every call ([backend/app/agent/loop.py](backend/app/agent/loop.py)). The checks every order needs run deterministically in Python first (pre-fetch): find the order, diff the last two versions, check feasibility for the current and the previous plan, and propose delivery options if the plan is infeasible. Ultra receives those results as evidence and keeps the loop for the optional tools and the final judgement. All maths is in Python:

| Tool | What it does |
|---|---|
| `find_order` | The order and every stored PO version |
| `diff_po_versions` | Old → new changes between two versions, with the delivery-pulled-forward alert |
| `check_delivery_feasibility` | Capacity and fabric lead time from the factory profile, minus other orders due in the same window (Ultra can also run a what-if, e.g. fabric already in-house) |
| `propose_delivery_options` | When the plan is infeasible: the earliest feasible date for the full quantity, and the split that ships on time |
| `check_compliance` | Tavily search for the destination country's import and labelling rules, with source URLs (cached per normalised country and product, per day) |
| `lookup_buyer` | Tavily search for buyer background, only for buyers with no earlier orders (cached per normalised name, per day) |

Each tool result gets an evidence id (E1, E2, …). The final risk report lists flags with severity, a one-line reason and evidence, plus an *Info checked* list. The flag policy in [backend/policy/risk_policy.yaml](backend/policy/risk_policy.yaml) is enforced in Python ([backend/app/services/risk_policy.py](backend/app/services/risk_policy.py)): evidence must point at a real tool result or a URL a tool returned; a compliance flag must name a concrete rule with a source URL; a buyer flag needs an adverse finding; anything short of that moves to *Info checked*. Severity follows a rubric: high only for an infeasible plan or a contract value change above 10% or 5,000; medium needs confirmation; low is minor. The email page shows every step: pre-fetched Python checks, Ultra's calls, tool inputs and results, model, tokens, latency and cost.

**Drafts and human-in-the-loop.** Super drafts the buyer reply and an internal note for production from facts assembled in Python: the order and its versions, the risk flags, the feasibility results and the delivery options (other buyers' orders are never included). A Python fact check then compares every date, quantity and price in the draft with those facts and the buyer's email, and flags anything else ([backend/app/services/fact_check.py](backend/app/services/fact_check.py)). Drafts wait in the approval queue: edit (re-checked on save), approve, or reject. Approving a draft with open violations needs an explicit acknowledgement. Approve marks the reply sent and records who and when; no real email leaves the system.

Factory capacity, lead times, ports and Incoterms live in [backend/profiles/](backend/profiles/) (India/Tiruppur and Bangladesh/Dhaka). The capacity figures are illustrative.

Model IDs, prices and per-task tier overrides come from environment variables (see [.env.example](.env.example)), so tiers can be swapped without code changes.

The router writes one row per call to the `llm_calls` table: task type, tier, model, input tokens, output tokens, latency and estimated cost. The UI trace panel and the numbers below are read from that table.

Model IDs, verified against Token Factory's `/v1/models` on 2026-10-08:

| Tier | Model ID | USD per 1M tokens (in / out) |
|---|---|---|
| Nano | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 0.06 / 0.24 |
| Super | `nvidia/nemotron-3-super-120b-a12b` | 0.30 / 0.90 |
| Ultra | `nvidia/Nemotron-3-Ultra-550b-a55b` | 1.00 / 3.00 |

Reasoning is switched per request with `chat_template_kwargs: {"enable_thinking": false}`. Classification, extraction and change detection run on Nano with thinking off: with it on, Nano spent its whole token budget reasoning and returned no JSON. Super and Ultra keep thinking available for drafting and risk reasoning.

First live numbers (10 labelled emails, Nano only so far): about $0.0003 and 9 seconds per email for classification plus extraction. See [backend/eval/report.md](backend/eval/report.md).

Live numbers with every model tier (10 labelled emails, cache off, 2026-10-10):

| Step | Model | Per email |
|---|---|---|
| Classification and extraction | Nano | about $0.0003 |
| Escalated fields (33% of emails, 1 field each) | Super | about $0.0001 |
| Risk agent with pre-fetch (2.2 calls, down from 4.1 with the full loop) | Ultra | $0.0165 (was $0.0210) |
| Reply and internal note drafts | Super | $0.0026 |

All 18 drafts passed the fact check (132 values checked, 0 violations).

## Architecture

```
web/ (Next.js)  ->  backend/app/api (FastAPI)  ->  agent loop  ->  tools  ->  services  ->  database
                                                       |
                                                 llm/router.py  ->  Nebius Token Factory (Nemotron Nano / Super / Ultra)
                                                 services/tavily_client.py  ->  Tavily
```

_To be filled: architecture diagram._

## Setup

Requirements: Python 3.11+, Node.js 20+.

```bash
cp .env.example .env          # then add NEBIUS_API_KEY and TAVILY_API_KEY
```

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m scripts.seed --analyse --agent --drafts   # load, analyse, assess and draft the 10 demo emails
uvicorn app.main:app --reload --port 8000
```

No Nebius key yet? Set `LLM_MODE=mock` in `.env`. Calls are then answered by a rule-based stand-in ([backend/app/llm/mock.py](backend/app/llm/mock.py)) with no network and no cost, so the whole pipeline runs. Mock results are labelled as such in the trace and the eval report.

Frontend:

```bash
cd web
npm install
npm run dev                   # http://localhost:3000
```

Checks (run from `backend/`):

```bash
pytest                           # unit tests, no network
python -m scripts.list_models    # NVIDIA model IDs served by Token Factory for your key
python -m scripts.smoke_llm      # one live call per Nemotron tier: model, tokens, latency, cost
python -m scripts.smoke_tavily   # one live Tavily search with source URLs
python -m eval.run_eval          # score extraction against the labelled cases, writes eval/report.md
python -m eval.run_eval --agent --compare-prefetch   # also the risk agent (with and without pre-fetch) and drafts
python -m scripts.rebuild_demo   # rebuild the local demo database, keeping the response cache
```

Docker (Postgres, API and web together, reading secrets from `.env`):

```bash
docker compose up --build        # web on :3000, API on :8000
```

## Cost controls for the public demo

- **Response cache:** live responses are cached by request hash, so re-running the same email costs nothing.
- **Daily spend cap:** `DAILY_SPEND_CAP_USD` defaults to $1/day (UTC). Once it is reached, live calls stop, cached responses still serve, and analysed emails show their stored result.
- **Rate limit:** endpoints that trigger LLM work allow `RATE_LIMIT_PER_MINUTE` requests per IP (default 10).

## Evaluation

Synthetic buyer emails modelled on real export paperwork live in [backend/eval/cases/](backend/eval/cases/), with hand-written expected outputs in [backend/eval/expected/](backend/eval/expected/). The first 10 cover a clean PO, revised and amended POs, one email mixing three requests, missing fields, contradictory quantities, a date changed inside a reply thread, day-first dates, and USD, EUR, GBP and AUD.

Every extracted field carries a confidence and the source quote it came from. Plain-Python rules then lower the confidence and flag the field for human review when the quote is not in the email, the quantities do not add up, or a required field is missing ([backend/app/services/review.py](backend/app/services/review.py)).

Each email that carries a PO is matched to its order by PO number and stored as a new version; earlier versions are never overwritten. [`diff_po_versions`](backend/app/agent/tools/diff_po_versions.py) is plain Python and reports quantity, price, delivery date, size ratio, colour and Incoterm changes with old and new values. Size breakdowns are compared as ratios, so scaling a colour up is a quantity change, not a ratio change. A delivery date moved earlier is flagged as **delivery pulled forward**, the most expensive change for an exporter. When a reply thread quotes the old value of an order we have not seen (for example "the 24 November date below no longer works"), the earlier version is rebuilt from the quote so the change is still visible.

_To be filled: results on Nemotron (live), growing to 40 cases with change-detection precision and recall, risk flag rate, and cost and latency per case._

## What we'd improve

_To be filled._

## License

MIT. See [LICENSE](LICENSE).
