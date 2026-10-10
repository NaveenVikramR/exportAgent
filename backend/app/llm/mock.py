"""Rule-based stand-in for the LLM, used when LLM_MODE=mock.

It is not a model. It reads the same prompt the model would get and answers in
the same JSON shape using generic regular expressions, so the whole pipeline
(prompt, validation, confidence review, storage, UI, eval) can run with no
network and no cost. It knows nothing about individual test cases and is
expected to get the messy ones wrong.
"""

import json
import re
from datetime import date
from typing import Any

from app.llm.prompts.common import EMAIL_CLOSE, EMAIL_OPEN
from app.llm.mock_agent import mock_plan
from app.llm.mock_drafts import mock_note, mock_reply
from app.llm.tasks import TaskType

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
)}
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
_DATE = (
    rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\s+\d{{4}}"
    rf"|{_MONTH}\s+\d{{1,2}},\s*\d{{4}}"
    r"|\d{2}/\d{2}/\d{4}"
    r"|\d{4}-\d{2}-\d{2})"
)
_COUNTRIES = {
    "germany": "Germany",
    "france": "France",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "united states": "United States",
    "usa": "United States",
    "australia": "Australia",
    "netherlands": "Netherlands",
    "spain": "Spain",
    "italy": "Italy",
    "canada": "Canada",
}
_COMPANY_SUFFIX = r"(?:GmbH|Pty Ltd|Ltd|Inc\.?|SAS|LLC|BV)"


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def mock_completion(
    task: TaskType, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """{"content": str | None, "tool_calls": [{"id", "name", "arguments"}]}"""
    if task in (TaskType.PLANNING, TaskType.RISK_REASONING):
        return mock_plan(messages, tools)
    if task is TaskType.DRAFT_REPLY:
        return {"content": mock_reply(messages)}
    if task is TaskType.DRAFT_INTERNAL_NOTE:
        return {"content": mock_note(messages)}
    text = _email_text(messages)
    if task is TaskType.CLASSIFY:
        return {"content": json.dumps(_classify(text))}
    if task is TaskType.EXTRACT:
        return {"content": json.dumps(_extract(text))}
    if task is TaskType.EXTRACT_ESCALATION:
        field = re.search(r'extract ONLY the field "(\w+)"', messages[0]["content"]).group(1)
        return {"content": json.dumps({field: _extract(text)[field]})}
    if task is TaskType.CHANGE_DETECTION:
        return {"content": json.dumps(_stated_changes(text))}
    return {"content": "[mock response: set LLM_MODE=live for model output]"}


def _email_text(messages: list[dict[str, Any]]) -> str:
    content = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    match = re.search(
        re.escape(EMAIL_OPEN) + r"(.*)" + re.escape(EMAIL_CLOSE), content, re.DOTALL
    )
    return (match.group(1) if match else content).strip()


def _classify(text: str) -> dict[str, Any]:
    def has(pattern: str) -> bool:
        return re.search(pattern, text, re.IGNORECASE) is not None

    intents: list[str] = []
    if has(r"\b(revised|revision|amendment|amended|rev\.?\s*\d)"):
        intents.append("po_revision")
    elif has(r"\b(purchase order|new order|po\s*(no|number|#)?[\s:#]*[A-Z]{1,4}[-/])"):
        intents.append("new_po")
    if has(r"(ex-factory|delivery|ship)[^.\n]{0,80}(now need|no longer|at the latest|bring forward|pull)"):
        # a date change in the message body outranks a PO that is only being referenced
        intents = ["delivery_change"] + [i for i in intents if i != "new_po"]
    if has(r"\b(lab dips?|fit samples?|samples?|approval)\b"):
        intents.append("sample_or_approval")
    if has(r"\b(packing list|bill of lading|bl copy|commercial invoice)\b"):
        intents.append("shipment_docs")
    if has(r"\b(where is|status of|has the vessel|when was it sent)\b"):
        intents.append("order_query")
    if has(r"\b(payment (is )?(due|overdue|received)|remittance)\b"):
        intents.append("payment")
    if not intents:
        intents = ["other"]

    po_intents = {"new_po", "po_revision", "delivery_change"}
    return {
        "category": intents[0],
        "intents": intents,
        "has_po_data": bool(po_intents & set(intents)),
        "summary": "Mock classification from keyword rules.",
        "confidence": 0.6,
    }


def _field(text: str, patterns: list[tuple[str, float]], flags: int = re.IGNORECASE) -> dict[str, Any]:
    for pattern, confidence in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return {
                "value": match.group(1).strip(),
                "confidence": confidence,
                "evidence": match.group(0).strip(),
            }
    return {"value": None, "confidence": 0, "evidence": None}


def _parse_date(raw: str) -> date | None:
    try:
        if match := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw):
            return date(int(match[1]), int(match[2]), int(match[3]))
        if match := re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", raw):
            return date(int(match[3]), int(match[2]), int(match[1]))
        if match := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", raw):
            return date(int(match[3]), _MONTHS[match[2][:3].lower()], int(match[1]))
        if match := re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", raw):
            return date(int(match[3]), _MONTHS[match[1][:3].lower()], int(match[2]))
    except (KeyError, ValueError):
        return None
    return None


def _line_items(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        header = line.split()
        if len(header) < 3 or not re.fullmatch(r"colou?r", header[0], re.IGNORECASE):
            continue
        if header[-1].lower() != "total":
            continue
        sizes = header[1:-1]
        items = []
        for row in lines[index + 1:]:
            match = re.fullmatch(r"\s*(\D+?)\s+((?:\d[\d,]*\s*)+)", row)
            if not match:
                break
            numbers = [int(n.replace(",", "")) for n in match.group(2).split()]
            if len(numbers) != len(sizes) + 1:
                break
            items.append(
                {
                    "colour": match.group(1).strip(),
                    "sizes": dict(zip(sizes, numbers[:-1])),
                    "quantity": numbers[-1],
                    "unit_price": None,
                }
            )
        return items
    return []


def _stated_changes(text: str) -> dict[str, Any]:
    """The first delivery date is the new one; a later, different one is the old one."""
    dates = []
    for match in re.finditer(rf"(?:ex-factory|delivery)[^\n\d]{{0,40}}({_DATE})", text, re.IGNORECASE):
        parsed = _parse_date(match.group(1))
        if parsed and parsed not in dates:
            dates.append(parsed)
    if len(dates) < 2:
        return {"changes": []}
    return {
        "changes": [
            {"field": "delivery_date", "old": dates[1].isoformat(), "new": dates[0].isoformat(), "evidence": None}
        ]
    }


def _extract(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}

    result["buyer"] = _field(
        text,
        [
            (r"^([A-Z][A-Z&.' ]+ (?:GMBH|PTY LTD|LTD|INC\.?|SAS|LLC|BV))\s*$", 0.9),
            (rf"([A-Z][\w&' ]+? {_COMPANY_SUFFIX})", 0.7),
        ],
        flags=re.MULTILINE,
    )
    result["po_number"] = _field(
        text,
        [(r"(?:PO|Purchase Order)\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Z]{1,4}[-/][A-Z0-9][A-Z0-9\-/]*\d)", 0.9)],
    )
    result["style"] = _field(
        text,
        [(r"style\s*(?:no\.?|ref\.?|number|#)?\s*[:#]?\s*([A-Z]{2,4}-[A-Z]{2,3}-\d{3,5})", 0.9)],
    )

    result["currency"] = _field(text, [(r"\b(USD|EUR|GBP|AUD)\b", 0.9)], flags=0)
    if result["currency"]["value"] is None:
        for symbol, code in (("£", "GBP"), ("€", "EUR"), ("$", "USD")):
            if symbol in text:
                result["currency"] = {"value": code, "confidence": 0.6, "evidence": symbol}
                break

    money = r"(?:USD|EUR|GBP|AUD)?\s*[$£€]?\s*"
    result["unit_price"] = _field(
        text,
        [
            (rf"(?:unit price|price per unit|unit cost|price)\s*:?\s*(?:is now\s*)?{money}(\d+\.\d{{2}})", 0.9),
            (r"(?:USD|EUR|GBP|AUD|[$£€])\s*(\d+\.\d{2})\s*(?:each|per piece|per pc|FOB|CIF)", 0.7),
        ],
    )

    quantity = _field(
        text,
        [
            (r"total\s*(?:quantity|qty|units)?\s*:?\s*([\d,]{3,})\s*(?:pcs|pieces|units)?", 0.9),
            (r"([\d,]{3,})\s*(?:pcs|pieces|units)\b", 0.6),
        ],
    )
    if quantity["value"] is not None:
        quantity["value"] = int(quantity["value"].replace(",", ""))
    result["total_quantity"] = quantity

    delivery = _field(
        text,
        [(rf"(?:ex-factory|delivery date|leave your factory)[^\n\d]{{0,40}}({_DATE})", 0.8)],
    )
    if delivery["value"] is not None:
        parsed = _parse_date(delivery["value"])
        delivery = (
            {**delivery, "value": parsed.isoformat()}
            if parsed
            else {"value": None, "confidence": 0, "evidence": None}
        )
    result["delivery_date"] = delivery

    incoterm = re.search(r"\b(FOB|CIF|CFR|EXW|DDP|DAP|FCA) ([A-Z][a-z]+(?: [A-Z][a-z]+)?)", text)
    if incoterm:
        evidence = incoterm.group(0)
        result["incoterms"] = {"value": incoterm.group(1), "confidence": 0.9, "evidence": evidence}
        result["port"] = {"value": incoterm.group(2), "confidence": 0.8, "evidence": evidence}
    else:
        result["incoterms"] = {"value": None, "confidence": 0, "evidence": None}
        result["port"] = {"value": None, "confidence": 0, "evidence": None}

    destination = {"value": None, "confidence": 0, "evidence": None}
    line = re.search(r"(?:Destination|Ship to)\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if line:
        for token in reversed(re.split(r",\s*", line.group(1).strip())):
            country = _COUNTRIES.get(token.strip().lower())
            if country:
                destination = {"value": country, "confidence": 0.8, "evidence": line.group(0).strip()}
                break
    result["destination_country"] = destination

    result["line_items"] = _line_items(text)
    return result
