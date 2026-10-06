# ExportAgent

An AI export desk for small and mid-size apparel and textile exporters. A buyer email arrives; ExportAgent classifies it, extracts the purchase order, detects what changed against the previous PO version, reasons about delivery and compliance risk, drafts a reply for a human to approve, and generates the Commercial Invoice and Packing List.

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps and Agents).

> Status: Milestone 1 (skeleton). The sections marked _to be filled_ are completed as the build progresses.

## How we use NVIDIA Nemotron + Nebius Token Factory

Every LLM call in ExportAgent is a runtime call to the Nebius Token Factory inference API, made with the OpenAI-compatible SDK from a single module, [backend/app/llm/router.py](backend/app/llm/router.py). Callers never name a model. They declare a task type, and the router picks the Nemotron tier from configuration.

| Task | Tier | Why |
|---|---|---|
| Email classification, field extraction, PO change detection | Nemotron Nano | Fast and cheap for high-volume structured work |
| Drafting buyer replies and internal notes | Nemotron Super | Better writing quality at moderate cost |
| Risk reasoning and multi-step planning in the agent loop | Nemotron Ultra | Strongest reasoning, used sparingly |

Model IDs, prices and per-task tier overrides come from environment variables (see [.env.example](.env.example)), so tiers can be swapped without code changes.

The router writes one row per call to the `llm_calls` table: task type, tier, model, input tokens, output tokens, latency and estimated cost. The UI trace panel and the numbers below are read from that table.

_To be filled: real per-model cost and latency numbers, tokens per processed email, evaluation results._

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
python -m scripts.seed --analyse   # load the 10 demo emails and analyse them
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

_To be filled: results on Nemotron (live), growing to 40 cases with change-detection precision and recall, risk flag rate, and cost and latency per case._

## What we'd improve

_To be filled._

## License

MIT. See [LICENSE](LICENSE).
