# ExportAgent — Kickoff Prompt for Claude Code

> Paste everything below the line into Claude Code (in VS Code, from an empty project folder).
> Tip: start Claude Code in **plan mode** for this first message so it proposes the plan before writing code.

---

You are my senior engineering partner. We are building **ExportAgent** for the **Nebius x NVIDIA Global AI Hackathon** (Devpost), track: **Best Apps and Agents**. Submission deadline: **Oct 30, 2026, 10:00 AM PDT**. I am a solo developer (final-year CS student, comfortable with Python/FastAPI, TypeScript/React/Next.js, PostgreSQL, agentic tool-calling loops).

Do **not** write the whole app in one go. First read this brief, then give me: (1) a short architecture proposal, (2) the folder structure, (3) a milestone plan matching the milestones below, and (4) any questions. Wait for my approval before writing code. After that, build one milestone at a time, run it, and commit with a clear message at the end of each milestone.

## 1. The product

**ExportAgent is an AI export desk for small and mid-size apparel/textile exporters** (10–200 person factories in Tiruppur, Dhaka, Ho Chi Minh City, Istanbul, etc.). Their merchandisers drown in buyer emails, purchase orders (POs), PO revisions, approvals, shipment deadlines, and export paperwork. Mistakes — a missed quantity change, a delivery date silently pulled forward — cost real money.

**The one core journey that must work flawlessly (this is the demo):**
1. A buyer email arrives (with or without a PO attachment), possibly mixing several requests.
2. The agent classifies it, extracts structured data (buyer, PO number, style, colours, sizes, quantities, unit price, currency, delivery date, Incoterms, port).
3. It matches it to an existing order or creates a new one, and **detects changes vs. the previous PO version** (quantity, price, delivery date, size ratio).
4. It reasons about **risk**: e.g. new delivery date vs. production capacity and lead time, quantity tolerance breaches, missing compliance items for the destination country.
5. It uses **Tavily** to look up live information where needed (destination-country import/labelling rules, buyer company background).
6. It drafts a professional reply to the buyer and a short internal note for the production team.
7. A **human approves/edits** the reply before anything is "sent" (human-in-the-loop — nothing is sent automatically).
8. It generates export documents as PDFs: **Commercial Invoice** and **Packing List**.

Everything else is secondary. One polished journey beats many half-built features.

## 2. Hard hackathon requirements (must be satisfied)

- The app must make **runtime calls to the Nebius Token Factory inference API** using **NVIDIA open models (Nemotron)**. Token Factory is OpenAI-compatible: use the official `openai` Python SDK with a custom `base_url`. Put the base URL and API key in `.env` (`NEBIUS_API_KEY`, `NEBIUS_BASE_URL`). **Verify the correct base URL and exact model IDs from the Nebius Token Factory docs or the `/v1/models` endpoint — do not guess.**
- Use **Tavily** with a real, functional runtime call (`TAVILY_API_KEY`) — this also makes us eligible for the Best Use of Tavily prize.
- Public GitHub repo with an **MIT LICENSE** file.
- README with setup instructions and a clear section: **"How we use NVIDIA Nemotron + Nebius Token Factory"**.
- A live hosted demo that stays working through **Dec 15, 2026** (judging period).
- All UI and docs in English.

## 3. Model routing (this is a key judging point — make it deliberate and visible)

Create a single `llm/router.py` module. Every LLM call goes through it and declares a **task type**; the router picks the model from config. Model IDs come from env vars so they can be swapped without code changes.

| Task | Model tier | Why |
|---|---|---|
| Email classification, field extraction, change detection | **Nemotron Nano** | Fast, cheap, high volume |
| Drafting buyer replies and internal notes | **Nemotron Super** | Good writing quality at moderate cost |
| Risk reasoning and multi-step planning in the agent loop | **Nemotron Ultra** | Serious reasoning, used sparingly |

The router must log, per call: task type, model, input tokens, output tokens, latency, estimated cost (prices in config). Expose these in a small "Agent trace" panel in the UI and aggregate them for the README.

## 4. Agent design

- A real **observe → reason → act → feed back** loop with tool calling (OpenAI-style function tools), chaining multiple tool calls per request.
- **Hard cap of 8 tool-call rounds** per request; set `max_tokens` on every call.
- Use **structured JSON outputs** validated with **Pydantic**; on validation failure, retry once with the error message, then route to human review.
- Every extracted field carries a **confidence**; low-confidence fields are highlighted for human review rather than silently accepted.
- Business rules (tolerance checks, date maths, totals, currency rounding) live in **plain Python tools**, not in prompts. The LLM decides *which* tools to call; the tools do the maths.

Suggested tools (refine in your proposal):
- `classify_email(email)`
- `extract_po_fields(email, attachments)`
- `find_order(buyer, po_number)` / `create_order(...)` / `update_order(...)`
- `diff_po_versions(old, new)` → structured change list
- `check_delivery_feasibility(order, new_date)` → uses capacity + lead time from factory config
- `check_compliance(destination_country, product_type)` → Tavily search + summary, with source URLs
- `lookup_buyer(company_name)` → Tavily
- `draft_reply(context)` / `draft_internal_note(context)`
- `generate_commercial_invoice(order)` / `generate_packing_list(order)` → PDF

## 5. Country / factory configuration

Keep country-specific and factory-specific details **pluggable via config files** (YAML/JSON): currency, document templates fields, default ports, Incoterms, factory capacity per week, standard lead times. The demo should show switching from an India (Tiruppur) profile to a Bangladesh (Dhaka) profile with no code changes.

## 6. Tech stack (propose changes if you have a strong reason)

- **Backend:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, PostgreSQL (SQLite allowed for local dev), Alembic migrations.
- **Frontend:** Next.js + TypeScript + Tailwind. Screens: Inbox (incoming buyer emails), Email detail with agent analysis, Orders list + order detail with PO version history and change highlights, Approval queue, Documents, Agent trace / cost panel.
- **PDF generation:** a Python library (e.g. ReportLab or WeasyPrint).
- **Email input for the MVP:** a seeded demo inbox plus "paste email / upload .eml or PDF". Real mailbox integration (IMAP/Gmail) is a stretch goal only — do not start with it.
- **Testing:** pytest for tools and rules.
- **Deployment target:** propose a setup that stays reliably online until Dec 15 (avoid free tiers that sleep or expire). Nebius Serverless Endpoints is a nice-to-have, not required.

## 7. Synthetic data and evaluation (required — numbers win)

- Create a **realistic synthetic dataset** modeled on real export document formats: ~40 buyer emails/PO scenarios including messy cases — revised POs, contradictory quantities, emails mixing three requests, delivery dates changed inside a reply thread, missing fields, different currencies.
- Each case has a hand-written **expected output** (labels) in a separate file.
- Build an **evaluation script** (`eval/run_eval.py`) that runs the agent on all cases and reports: field-extraction accuracy, change-detection precision/recall, correct risk flag rate, average cost per case, average latency, and per-model token usage. Output a markdown report we can paste into the README.
- Never hardcode answers for specific test cases.

## 8. Credit discipline (I have about $50 in Token Factory credits)

- Default to **Nano during development**; make the tier per task configurable.
- Cache LLM responses during development (keyed by prompt hash) so re-runs don't re-spend.
- Trim conversation history passed to the model.
- Show a running cost total in the trace panel.

## 9. Engineering standards

- Clean separation: `llm/` (router, prompts), `agent/` (loop, tools), `services/` (orders, documents, compliance), `api/`, `web/`.
- Secrets only in `.env`; commit a `.env.example`; add `.env` to `.gitignore` **before the first commit**.
- Small, frequent commits with clear messages (the commit history proves work was done during the hackathon).
- Sensible error handling: Token Factory/Tavily failures show a clear message, never crash the UI.

## 10. Milestones

1. **Skeleton** — repo, MIT license, `.gitignore`, `.env.example`, FastAPI + Next.js running, DB models, one test call to Nemotron via Token Factory through the router (prints model, tokens, latency).
2. **Extraction** — classify + extract PO fields from emails with Pydantic validation and confidence scores; seed 10 demo emails.
3. **Orders + change detection** — order store, PO version history, `diff_po_versions`, UI highlighting changes.
4. **Agent loop + risk** — full tool-calling loop, delivery feasibility, Tavily compliance and buyer lookups, agent trace panel.
5. **Drafts + human-in-the-loop** — reply and internal note drafting, approval queue with edit/approve/reject.
6. **Documents** — Commercial Invoice and Packing List PDFs.
7. **Evaluation** — 40-case dataset, eval script, markdown report.
8. **Polish + deploy** — UI polish, country profile switch, deployment, README (setup, architecture diagram, model routing table with real cost/latency numbers, eval results, "How we use Nemotron + Token Factory", "What we'd improve").

Start now with the architecture proposal, folder structure, milestone plan and your questions. Do not write code until I approve.