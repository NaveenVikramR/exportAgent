"""Deterministic clean-up of extracted values, applied before review and order matching.

- PO numbers: a revision suffix ("Rev A", "R2", "(REV 2)", "Amendment 1") is split off,
  so a revision matches its order. The revision is kept separately.
- Amounts: a decimal comma ("9,80", "41.160,00") is read as a decimal.
- Colour names: a colour the model shortened ("Navy" for "Navy Stars") is restored
  from the email when the full name stands next to the same quantity.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.schemas.extraction import POExtraction

_REVISION_SUFFIX = re.compile(
    r"""[\s\-_/]*[(\[]?\s*
        (?:rev(?:ision)?|r|amendment|amend|amd|version|ver|v)
        \.?\s*[-#:.]?\s*
        (?P<rev>[A-Z]|\d{1,3})
        \s*[)\]]?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def split_po_revision(raw: str) -> tuple[str, str | None]:
    """("CL-7731 Revision A") -> ("CL-7731", "A"); a PO without a suffix is returned as is."""
    text = " ".join(raw.split())
    match = _REVISION_SUFFIX.search(text)
    if not match:
        return text, None
    base = text[: match.start()].strip(" -_/")
    # Never strip a PO down to nothing or to a bare prefix like "PO".
    if len(re.sub(r"[^A-Za-z0-9]", "", base)) < 4 or not re.search(r"\d", base):
        return text, None
    return base, match.group("rev").upper()


_EUROPEAN = re.compile(r"^\d{1,3}(?:\.\d{3})+,\d+$|^\d+,\d{1,2}$")


def parse_amount(value: object) -> object:
    """'9,80' -> '9.80' and '41.160,00' -> '41160.00'; anything else is returned unchanged."""
    if not isinstance(value, str):
        return value
    text = value.strip().replace(" ", "").replace(" ", "")
    if _EUROPEAN.match(text):
        return text.replace(".", "").replace(",", ".")
    return value


def _quantity_forms(quantity: int) -> list[str]:
    forms = {f"{quantity}", f"{quantity:,}", f"{quantity:,}".replace(",", "."), f"{quantity:,}".replace(",", " ")}
    return sorted(forms, key=len, reverse=True)


def restore_colour_names(extraction: POExtraction, text: str) -> list[str]:
    """Longer colour names written next to the same quantity in the email. Returns notes."""
    notes = []
    for item in extraction.line_items:
        if not item.colour or not item.quantity:
            continue
        for form in _quantity_forms(item.quantity):
            pattern = rf"(?<![\w-])({re.escape(item.colour)}(?:[ \-][A-Za-z][\w'-]*){{1,3}})\s*[:=\-–]?\s*{re.escape(form)}(?![\d,.])"
            match = re.search(pattern, text, re.IGNORECASE)
            if match and len(match.group(1)) > len(item.colour):
                full = match.group(1).strip()
                notes.append(f"Colour '{item.colour}' restored to '{full}' from the email.")
                item.colour = full
                break
    return notes


def normalise_extraction(extraction: POExtraction, text: str) -> list[str]:
    """Clean the extraction in place; returns notes on what changed."""
    notes = []
    po = extraction.po_number.value
    if po:
        base, revision = split_po_revision(po)
        if revision:
            extraction.po_number.value = base
            extraction.po_revision = revision
            notes.append(f"PO number '{po}' read as PO {base}, revision {revision}.")
    notes += restore_colour_names(extraction, text)
    country = extraction.destination_country.value
    if isinstance(country, str) and _country_key(country) in _COUNTRY_NAMES:
        extraction.destination_country.value = _COUNTRY_NAMES[_country_key(country)]
    return notes


def _country_key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", plain.casefold())


# Short forms mapped to one name, so the same country never shows up as a change between versions.
_COUNTRY_NAMES = {
    "usa": "United States", "us": "United States", "unitedstatesofamerica": "United States",
    "uk": "United Kingdom", "greatbritain": "United Kingdom", "gb": "United Kingdom",
    "uae": "United Arab Emirates", "deutschland": "Germany", "espana": "Spain", "nederland": "Netherlands",
    "thenetherlands": "Netherlands", "holland": "Netherlands",
}


def to_decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(parse_amount(value)))
    except (InvalidOperation, TypeError):
        return None
