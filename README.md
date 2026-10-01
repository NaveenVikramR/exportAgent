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
uvicorn app.main:app --reload --port 8000
```

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
```

## Evaluation

_To be filled: 40-case synthetic dataset, extraction accuracy, change-detection precision and recall, risk flag rate, cost and latency per case._

## What we'd improve

_To be filled._

## License

MIT. See [LICENSE](LICENSE).
