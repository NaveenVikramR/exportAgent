# Demo video: voiceover script

Silent footage: `exportagent-demo.mp4` (1920×1080, H.264, 30 fps), with one clip per segment in `clips/`.
Subtitles with the same text: `exportagent-demo.srt`. Times below are from the recorded take.
Read at a calm pace, about 2.5 words a second; each line fits its time on screen.

## 0:00–0:20 · Inbox, open the revised PO, read the buyer's email
Clip: `clips/01_inbox_email.mp4`

- **0:00** This is ExportAgent, an AI export desk for apparel and textile exporters.
- **0:06** A German buyer has just sent a revised purchase order: Rev 1 of PO NW-45120.
- **0:13** Here is their email, with the purchase order attached as a PDF.

## 0:20–0:51 · Extracted fields, then the changes between PO versions
Clip: `clips/02_fields_changes.mp4`

- **0:20** Nemotron Nano extracted every field, with a confidence score and the exact source quote.
- **0:27** Python then checks each one: is the quote really in the email, and do the sizes add up?
- **0:34** The order keeps every version, and Python compares them field by field.
- **0:40** The total is up 1,500 pieces, and the ex-factory date moved 15 days earlier.
- **0:46** Navy alone is up 33%. Every change goes to the risk check.

## 0:51–1:05 · Risk card: 4,186 pcs short, judged by Nemotron Ultra; the trace
Clip: `clips/03_risk_trace.mp4`

- **0:51** Python found the new plan infeasible, so this run escalated to Nemotron Ultra.
- **0:57** The factory is 4,186 pieces short of free capacity.
- **1:01** The trace shows every step, and the Python result behind each flag.

## 1:05–1:15 · Compliance check: Tavily web search with its sources
Clip: `clips/04_compliance_tavily.mp4`

- **1:05** Ultra chose to check Germany's import rules with a Tavily web search.
- **1:10** Its sources are kept as evidence. The labelling rule is listed under Info checked.

## 1:15–1:28 · Draft reply: two delivery options computed in Python, fact check passed
Clip: `clips/05_draft_reply.mp4`

- **1:15** Nemotron Super drafted the reply. A Python fact check verified all 14 values in it.
- **1:21** Both delivery options, the full quantity on 8 December or a split shipment, were computed in Python.

## 1:28–1:33 · Approve the reply (nothing is emailed)
Clip: `clips/06_approve.mp4`

- **1:28** A person approves every reply. Nothing is emailed automatically.

## 1:33–1:50 · Factory profiles: Tiruppur infeasible, Dhaka feasible
Clip: `clips/07_profiles.mp4`

- **1:33** Capacity, lead times and invoice formats live in factory profiles.
- **1:39** The same revision is infeasible in Tiruppur, but feasible in Dhaka, at 72% of free capacity.
- **1:45** Switching profiles changes the exporter, the port and the paperwork.

## 1:50–2:06 · Record the split shipment, generate the invoice and packing list
Clip: `clips/08_decision_documents.mp4`

- **1:50** The buyer accepts the split shipment, so we record that decision.
- **1:56** ExportAgent generates an invoice and a packing list for each shipment.
- **2:01** Every number is computed in Python. Anything unknown prints as TO BE CONFIRMED.

## 2:06–2:35 · How it works: routing and measured numbers
Clip: `clips/09_how_it_works.mp4`

- **2:06** Every model call runs on Nebius Token Factory. Nano reads, Super drafts and judges risk.
- **2:13** Ultra is used only when a trigger fires: about 21% of risk runs.
- **2:20** Measured live, a whole email costs under one cent: $0.0094.
- **2:27** On a held-out test set, it found every high-risk issue.

## 2:35–2:44 · Dashboard: the closing shot
Clip: `clips/10_dashboard.mp4`

- **2:35** ExportAgent: every buyer email read, checked and answered, with a person in control.
