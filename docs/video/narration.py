"""Write voiceover.md and exportagent-demo.srt from the narration below.

Each line is anchored to its segment's start in segments.json (written by build_video.py),
so re-recording the footage keeps the subtitles in sync.
    python narration.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent

# (segment key, seconds after the segment starts, seconds on screen, text)
NARRATION = [
    ("01_inbox_email", 0.0, 6.5, "This is ExportAgent, an AI export desk for apparel and textile exporters."),
    ("01_inbox_email", 6.5, 7.0, "A German buyer has just sent a revised purchase order: Rev 1 of PO NW-45120."),
    ("01_inbox_email", 13.5, 6.5, "Here is their email, with the purchase order attached as a PDF."),
    ("02_fields_changes", 0.0, 7.0, "Nemotron Nano extracted every field, with a confidence score and the exact source quote."),
    ("02_fields_changes", 7.0, 7.0, "Python then checks each one: is the quote really in the email, and do the sizes add up?"),
    ("02_fields_changes", 14.0, 6.5, "The order keeps every version, and Python compares them field by field."),
    ("02_fields_changes", 20.5, 5.5, "The total is up 1,500 pieces, and the ex-factory date moved 15 days earlier."),
    ("02_fields_changes", 26.0, 5.4, "Navy alone is up 33%. Every change goes to the risk check."),
    ("03_risk_trace", 0.0, 5.0, "Python found the new plan infeasible, so this run escalated to Nemotron Ultra."),
    ("03_risk_trace", 5.0, 4.6, "The factory is 4,186 pieces short, and the contract value is up 12.5%."),
    ("03_risk_trace", 9.6, 4.8, "The trace shows every step, and the Python result behind each flag."),
    ("04_compliance_tavily", 0.0, 5.0, "Ultra chose to check Germany's labelling rules with a Tavily web search."),
    ("04_compliance_tavily", 5.0, 5.4, "Every source is listed under the finding, as a link you can open."),
    ("05_draft_reply", 0.0, 6.0, "Nemotron Super drafted the reply. A Python fact check verified all 14 values in it."),
    ("05_draft_reply", 6.0, 6.4, "Both delivery options, the full quantity on 8 December or a split shipment, were computed in Python."),
    ("06_approve", 0.0, 5.0, "A person approves every reply. Nothing is emailed automatically."),
    ("07_profiles", 0.0, 6.5, "Capacity, lead times and invoice formats live in factory profiles."),
    ("07_profiles", 6.5, 6.0, "The same revision is infeasible in Tiruppur, but feasible in Dhaka, at 72% of free capacity."),
    ("07_profiles", 12.5, 5.0, "Switching profiles changes the exporter, the port and the paperwork."),
    ("08_decision_documents", 0.0, 5.5, "The buyer accepts the split shipment, so we record that decision."),
    ("08_decision_documents", 5.5, 5.0, "ExportAgent generates an invoice and a packing list for each shipment."),
    ("08_decision_documents", 10.5, 5.6, "Every number is computed in Python. Anything unknown prints as TO BE CONFIRMED."),
    ("09_how_it_works", 0.0, 7.0, "Every model call runs on Nebius Token Factory. Nano reads, Super drafts and judges risk."),
    ("09_how_it_works", 7.0, 7.0, "Ultra is used only when a trigger fires: about 21% of risk runs."),
    ("09_how_it_works", 14.0, 7.0, "Measured live, a whole email costs under one cent: $0.0094."),
    ("09_how_it_works", 21.0, 7.4, "On a held-out test set, it found every high-risk issue."),
    ("10_dashboard", 0.0, 8.6, "ExportAgent: every buyer email read, checked and answered, with a person in control."),
]


def stamp(seconds: float, srt: bool) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}" if srt else f"{m}:{s:02d}"


segments = {s["key"]: s for s in json.loads((HERE / "segments.json").read_text())}
cues = []
for key, offset, length, text in NARRATION:
    seg = segments[key]
    start = seg["start"] + offset
    end = min(start + length, seg["end"])
    cues.append((key, start, end, text))

srt = []
for i, (_, start, end, text) in enumerate(cues, 1):
    srt += [str(i), f"{stamp(start, True)} --> {stamp(end, True)}", text, ""]
(HERE / "exportagent-demo.srt").write_text("\n".join(srt), encoding="utf-8")

md = ["# Demo video: voiceover script", "",
      "Silent footage: `exportagent-demo.mp4` (1920×1080, H.264, 30 fps), with one clip per segment in `clips/`.",
      "Subtitles with the same text: `exportagent-demo.srt`. Times below are from the recorded take.",
      "Read at a calm pace, about 2.5 words a second; each line fits its time on screen.", ""]
for key, seg in segments.items():
    md += [f"## {stamp(seg['start'], False)}–{stamp(seg['end'], False)} · {seg['title']}",
           f"Clip: `clips/{key}.mp4`", ""]
    for k, start, end, text in cues:
        if k == key:
            md.append(f"- **{stamp(start, False)}** {text}")
    md.append("")
(HERE / "voiceover.md").write_text("\n".join(md), encoding="utf-8")
print(f"{len(cues)} cues, ends at {stamp(cues[-1][2], False)}")
