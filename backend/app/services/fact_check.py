"""Checks a draft against its sources: every date, quantity and price must appear in them.

Sources are the facts given to the drafting model (extracted order data, order
history, tool results) and the buyer's email itself. Anything else in the draft
is reported as a violation for the reviewer. Pure Python, no model involved.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s+(\d{4}))?"

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUMERIC = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")  # day first, as export paperwork writes it
_DAY_MONTH = re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MONTH}{_YEAR}\b", re.IGNORECASE)
_MONTH_DAY = re.compile(rf"\b{_MONTH}\s+{_DAY}{_YEAR}\b", re.IGNORECASE)

_AMOUNT = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
# An optional k/m suffix scales the amount ("$5k" is 5,000).
_MONEY = re.compile(rf"(?:USD|EUR|GBP|AUD|INR|US\$|A\$|\$|€|£)\s?{_AMOUNT}([km])?\b", re.IGNORECASE)
_SCALE = {"k": 1000, "m": 1_000_000}
# Amounts with cents and thousands separators but no currency sign, e.g. "65,475.00"
_PLAIN_AMOUNT = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+\.\d{2})(?![\d])")
_UNIT_PRICE = re.compile(r"\b(\d+\.\d{2})\s*(?:per piece|per pc|/pc|/piece|each)\b", re.IGNORECASE)
_QUANTITY = re.compile(r"\b(\d{1,3}(?:,\d{3})+|\d+)\s*(?:pcs|pieces|pc|units|garments)\b", re.IGNORECASE)
_BIG_NUMBER = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+)(?![\d.,]*\d)")
_ANY_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

DateKey = tuple[int | None, int, int]


def _number(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "")).normalize()
    except InvalidOperation:
        return None


def _dates(text: str) -> list[tuple[str, DateKey, tuple[int, int]]]:
    """(matched text, (year or None, month, day), span) for every date-looking mention."""
    found = []
    for match in _ISO.finditer(text):
        found.append((match.group(0), (int(match[1]), int(match[2]), int(match[3])), match.span()))
    for match in _NUMERIC.finditer(text):
        found.append((match.group(0), (int(match[3]), int(match[2]), int(match[1])), match.span()))
    for match in _DAY_MONTH.finditer(text):
        year = int(match[3]) if match[3] else None
        found.append((match.group(0), (year, _MONTHS[match[2][:3].lower()], int(match[1])), match.span()))
    for match in _MONTH_DAY.finditer(text):
        year = int(match[3]) if match[3] else None
        found.append((match.group(0), (year, _MONTHS[match[1][:3].lower()], int(match[2])), match.span()))
    valid = []
    for raw, (year, month, day), span in found:
        try:
            date(year or 2000, month, day)
        except ValueError:
            continue
        valid.append((raw, (year, month, day), span))
    return valid


def _walk(value: Any) -> list[str]:
    """Every scalar in a nested structure, as text."""
    if isinstance(value, dict):
        return [item for v in value.values() for item in _walk(v)]
    if isinstance(value, (list, tuple)):
        return [item for v in value for item in _walk(v)]
    return [] if value is None or isinstance(value, bool) else [str(value)]


class Sources:
    """The values a draft may mention."""

    def __init__(self, facts: dict[str, Any], source_text: str) -> None:
        texts = _walk(facts) + [source_text]
        self.dates: set[DateKey] = set()
        self.month_days: set[tuple[int, int]] = set()
        self.numbers: set[Decimal] = set()
        for text in texts:
            for _, (year, month, day), _ in _dates(text):
                if year:
                    self.dates.add((year, month, day))
                self.month_days.add((month, day))
            for raw in _ANY_NUMBER.findall(text):
                if (number := _number(raw)) is not None:
                    self.numbers.add(number)

    def has_date(self, key: DateKey) -> bool:
        year, month, day = key
        return (year, month, day) in self.dates if year else (month, day) in self.month_days

    def has_number(self, value: Decimal) -> bool:
        return value in self.numbers


_GROUP_SPACE = re.compile(r"(?<=\d)[   ](?=\d{3}\b)")
_SPECIAL_SPACE = re.compile(r"[   ]")
_SPECIAL_HYPHEN = re.compile(r"[‐‑]")


def normalise_text(text: str) -> str:
    """Typographic variants models produce: "13 500" is 13,500 and a non-breaking hyphen is a hyphen."""
    text = _GROUP_SPACE.sub(",", text)
    return _SPECIAL_HYPHEN.sub("-", _SPECIAL_SPACE.sub(" ", text))


def fact_check(draft: str, facts: dict[str, Any], source_text: str) -> dict[str, Any]:
    draft = normalise_text(draft)
    sources = Sources(facts, normalise_text(source_text))
    violations: list[dict[str, str]] = []
    checked = 0
    taken: list[tuple[int, int]] = []

    def overlaps(span: tuple[int, int]) -> bool:
        return any(span[0] < end and start < span[1] for start, end in taken)

    for raw, key, span in _dates(draft):
        if overlaps(span):
            continue
        taken.append(span)
        checked += 1
        if not sources.has_date(key):
            violations.append({"kind": "date", "text": raw, "detail": "This date is not in the order data or the email."})

    for kind, pattern in (("price", _MONEY), ("price", _PLAIN_AMOUNT), ("price", _UNIT_PRICE), ("quantity", _QUANTITY), ("quantity", _BIG_NUMBER)):
        for match in pattern.finditer(draft):
            if overlaps(match.span()):
                continue
            taken.append(match.span())
            value = _number(match.group(1))
            suffix = match.group(2) if pattern is _MONEY else None
            if value is not None and suffix:
                value = (value * _SCALE[suffix.lower()]).normalize()
            if value is None:
                continue
            checked += 1
            if not sources.has_number(value):
                violations.append({"kind": kind, "text": match.group(0),
                                   "detail": f"This {kind} is not in the order data or the email."})

    return {"checked": checked, "violations": violations}
