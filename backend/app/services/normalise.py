"""Deterministic clean-up of extracted values, applied before review and order matching.

- PO numbers: a revision suffix ("Rev A", "REVISION 2", "Amendment No. 1", "R3", "v2") is split
  off, so a revision matches its order. The revision is kept separately; one the model dropped
  is recovered from the email. A bare letter ("-A") is only a revision when the base PO is a
  known order (see order_matching).
- Dates: a numeric date whose day and month are both 12 or under ("03/04/2027") is read with
  the convention of the buyer's country and any unambiguous date in the same email; if those
  are missing or disagree, the date is flagged for review instead of guessed.
- Colours: a name that picked up the wording around it ("Nachtblau to") is cleaned, and a
  colour the email drops or cancels is recorded as removed (see removed_colours).
- Amounts: a decimal comma ("9,80", "41.160,00") is read as a decimal.
- Colour names: a colour the model shortened ("Navy" for "Navy Stars") is restored
  from the email when the full name stands next to the same quantity.
"""

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from app.schemas.extraction import POExtraction
from app.services.places import names_country

_REVISION_MARKER = r"(?:rev(?:ision)?|r|amendment|amend|amdt|amd|version|ver|v)"
_REVISION_NUMBER = r"\.?\s*(?:no\.?|nr\.?|number)?\s*[-#:.]?\s*(?P<rev>[A-Z]|\d{1,3})"
_REVISION_SUFFIX = re.compile(
    rf"[\s\-_/]*[(\[]?\s*{_REVISION_MARKER}{_REVISION_NUMBER}\s*[)\]]?\s*$",
    re.IGNORECASE,
)
# "-A", "/B": a single letter after the PO; a revision only if the base is a known order.
_LETTER_SUFFIX = re.compile(r"[\-_/ ](?P<rev>[A-Z])$")


def _plausible_base(base: str) -> bool:
    # Never strip a PO down to nothing or to a bare prefix like "PO".
    return len(re.sub(r"[^A-Za-z0-9]", "", base)) >= 4 and re.search(r"\d", base) is not None


def split_letter_suffix(raw: str) -> tuple[str, str | None]:
    """("AB-1001-A") -> ("AB-1001", "A"). Only meaningful when "AB-1001" is a known order."""
    text = raw.strip()
    match = _LETTER_SUFFIX.search(text)
    if not match or not _plausible_base(text[: match.start()]):
        return raw, None
    return text[: match.start()], match.group("rev")


def revision_in_text(po_number: str, text: str) -> str | None:
    """The revision written next to the PO number in the email, e.g. "BW-508 Rev B" -> "B"."""
    pattern = (
        r"(?<![A-Za-z0-9])" + r"\s*".join(map(re.escape, re.sub(r"\s+", "", po_number)))
        + rf"[\s\-_/]*[(\[]?\s*{_REVISION_MARKER}{_REVISION_NUMBER}(?![A-Za-z0-9])"
    )
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group("rev").upper() if match else None


def split_po_revision(raw: str) -> tuple[str, str | None]:
    """("CL-7731 Revision A") -> ("CL-7731", "A"); a PO without a suffix is returned as is."""
    text = " ".join(raw.split())
    match = _REVISION_SUFFIX.search(text)
    if not match:
        return text, None
    base = text[: match.start()].strip(" -_/")
    if not _plausible_base(base):
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
            # the longer name must not pick up the wording after it ("Heather Charcoal to 900")
            full = clean_colour_name(match.group(1).strip()) if match else ""
            if match and len(full) > len(item.colour):
                notes.append(f"Colour '{item.colour}' restored to '{full}' from the email.")
                item.colour = full
                break
    return notes


# Words a model sometimes keeps with a colour name: "Nachtblau to 1,600", "increase Navy".
_COLOUR_EDGE_WORDS = (
    "to", "from", "at", "by", "now", "increased", "reduced", "becomes", "is", "qty", "quantity", "pcs",
    "increase", "reduce", "change", "make", "add", "set", "raise", "lower", "cut",
)
_EDGE = "|".join(_COLOUR_EDGE_WORDS)
_COLOUR_TRAILING = re.compile(rf"(?:\s+(?:{_EDGE}))+\s*[:\-]?\s*$", re.IGNORECASE)
_COLOUR_LEADING = re.compile(rf"^\s*(?:(?:{_EDGE})\s+)+(?:the\s+)?", re.IGNORECASE)


def clean_colour_name(colour: str) -> str:
    """'Nachtblau to' -> 'Nachtblau'; 'increase Navy' -> 'Navy'. A name never becomes empty."""
    cleaned = _COLOUR_LEADING.sub("", _COLOUR_TRAILING.sub("", colour)).strip(" :-")
    return cleaned or colour


_REMOVE_VERBS = r"(?:drop|cancel|remove|delete|discontinue|withdraw)"
_REMOVED_WORDS = r"(?:cancel(?:l)?ed|dropped|removed|deleted|discontinued|withdrawn)"
_NEGATION = re.compile(r"\b(?:not|no longer|don't|do not|instead of)\b", re.IGNORECASE)


def removed_colours(text: str, colours: list[str]) -> list[str]:
    """Colours of the order that the email drops or cancels: "please drop Mustard",
    "Rust is cancelled", "Mustard to 0"."""
    found = []
    for colour in colours:
        name = r"\s+".join(map(re.escape, colour.split()))
        patterns = (
            rf"\b{_REMOVE_VERBS}(?:s|ped|ping|led|ling|ed|ing|d)?\b[^.;,\n]{{0,30}}?(?<![\w-]){name}(?![\w-])",
            rf"(?<![\w-]){name}(?![\w-])[^.;,\n]{{0,25}}?\b{_REMOVED_WORDS}\b",
            rf"(?<![\w-]){name}(?![\w-])\s*(?:to|:|=|->)\s*0\s*(?:pcs|pieces|units)?(?![\d.,])",
        )
        match = next((m for p in patterns if (m := re.search(p, text, re.IGNORECASE))), None)
        clause = text[max(0, match.start() - 15): match.end()] if match else ""
        if match and not _NEGATION.search(clause):
            found.append(colour)
    return found


def normalise_extraction(extraction: POExtraction, text: str) -> list[str]:
    """Clean the extraction in place; returns notes on what changed."""
    notes = []
    po = extraction.po_number.value
    if po:
        base, revision = split_po_revision(po)
        if not revision and not extraction.po_revision:
            # the model copied the PO without the revision written next to it
            revision = revision_in_text(base, text)
        if revision:
            extraction.po_number.value = base
            extraction.po_revision = revision
            notes.append(f"PO number '{po}' read as PO {base}, revision {revision}.")
    style = extraction.style.value
    if isinstance(style, str) and not extraction.po_number.value:
        # "BW-508 Rev B" read as the style: the revision suffix marks it as an order reference.
        base, revision = split_po_revision(style)
        if revision:
            extraction.po_number.value, extraction.po_revision = base, revision
            extraction.style.value = None
            notes.append(f"Style '{style}' read as PO {base}, revision {revision}.")
    notes += _style_is_not_the_po(extraction, text)
    for item in extraction.line_items:
        if item.colour and clean_colour_name(item.colour) != item.colour:
            notes.append(f"Colour '{item.colour}' read as '{clean_colour_name(item.colour)}'.")
            item.colour = clean_colour_name(item.colour)
    notes += restore_colour_names(extraction, text)
    country = extraction.destination_country.value
    if isinstance(country, str) and _country_key(country) in _COUNTRY_NAMES:
        extraction.destination_country.value = _COUNTRY_NAMES[_country_key(country)]
        country = extraction.destination_country.value
    if isinstance(country, str) and not names_country(text, country):
        # Inferred, not stated (e.g. from the buyer's name). It would also settle ambiguous
        # dates below, so no destination rather than a guess.
        extraction.destination_country.value, extraction.destination_country.evidence = None, None
        notes.append(f"Destination '{country}' is not stated in the email; left empty.")
    notes += resolve_delivery_date(extraction, text)
    return notes


def _code_key(code: str) -> str:
    return re.sub(r"[^a-z0-9]", "", code.casefold())


_STYLE_LABEL = r"(?:style|art(?:icle|ikel)?|item|model|ref(?:erence)?)\s*(?:no\.?|nr\.?|number|#|code)?\s*[:#.-]?\s*"


def _style_is_not_the_po(extraction: POExtraction, text: str) -> list[str]:
    """The PO number copied into the style field, when the email names no style: drop it,
    so a follow-up keeps the order's style instead of recording a false style change."""
    style, po = extraction.style.value, extraction.po_number.value
    if not (isinstance(style, str) and isinstance(po, str)):
        return []
    style_base, _ = split_po_revision(style)
    if _code_key(style_base) != _code_key(po):
        return []
    if re.search(_STYLE_LABEL + re.escape(style_base), text, re.IGNORECASE):
        return []  # the email really calls it the style
    extraction.style.value, extraction.style.evidence = None, None
    return [f"Style '{style}' is the PO number; the email names no style."]


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


# --- dates ---------------------------------------------------------------------------------

# Countries that write the month first; year-first dates (Japan, China, ISO) are unambiguous anyway.
_MONTH_FIRST = {"United States", "Philippines"}
# Countries where both orders are common: never resolved from the country alone.
_MIXED = {"Canada"}
_NUMERIC_DATE = re.compile(r"(?<![\d./-])(\d{1,4})([./-])(\d{1,2})\2(\d{2,4})(?!\d|[./-]\d)")


def _numeric_dates(text: str) -> list[tuple[int, int, int, bool]]:
    """(first, second, year, year_first) for every numeric date in the text."""
    found = []
    for match in _NUMERIC_DATE.finditer(text):
        a, b, c = match.group(1), match.group(3), match.group(4)
        if len(a) == 4:
            if len(c) <= 2:
                found.append((int(b), int(c), int(a), True))
            continue
        if len(a) > 2:
            continue
        year = int(c) + 2000 if len(c) == 2 else int(c)
        if 2000 <= year <= 2099:
            found.append((int(a), int(b), year, False))
    return found


def date_convention(text: str, country: str | None) -> str | None:
    """'DMY', 'MDY' or None (unknown or contradictory) for the numeric dates in this email.

    Evidence: dates in the email that can only be read one way (13/02, 02/13), and the
    convention of the buyer's country. If they disagree, nothing is assumed.
    """
    from_text = set()
    for first, second, _year, year_first in _numeric_dates(text):
        if year_first:
            continue
        if first > 12 >= second:
            from_text.add("DMY")
        elif second > 12 >= first:
            from_text.add("MDY")
    from_country = None
    if country:
        name = _COUNTRY_NAMES.get(_country_key(country), country)
        if name in _MONTH_FIRST:
            from_country = "MDY"
        elif name not in _MIXED:
            from_country = "DMY"
    if len(from_text) > 1 or (from_text and from_country and from_text != {from_country}):
        return None
    return next(iter(from_text), None) or from_country


def resolve_date(iso: str, text: str, convention: str | None) -> tuple[str, bool]:
    """(date, ambiguous) for a date the model returned as ISO, checked against how the email wrote it.

    Only a date written in the email as an ambiguous numeric date (both parts 12 or under,
    not equal) is affected: it is read with `convention`, or reported as ambiguous.
    """
    try:
        year, month, day = (int(part) for part in str(iso).split("-"))
    except ValueError:
        return iso, False
    if month == day or month > 12 or day > 12:
        return iso, False
    written = [d for d in _numeric_dates(text) if d[2] == year and {d[0], d[1]} == {month, day}]
    if not written or any(d[3] for d in written):
        return iso, False
    if convention is None:
        return iso, True
    first, second = written[0][0], written[0][1]
    day, month = (first, second) if convention == "DMY" else (second, first)
    return f"{year:04d}-{month:02d}-{day:02d}", False


_PARTIAL_DATE = re.compile(r"(?<![\d./-])(\d{1,2})([./-])(\d{1,2})(?![./-]?\d)")
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def same_day_and_month(a: str, b: str) -> bool:
    """Two ISO dates that are readings of the same written date: equal day and month in either
    order, the year possibly guessed differently (a date written as "15/02" or "03/04")."""
    try:
        _ya, ma, da = (int(x) for x in str(a).split("-"))
        _yb, mb, db = (int(x) for x in str(b).split("-"))
    except ValueError:
        return False
    return {ma, da} == {mb, db}


def mentions_date(text: str, iso: str) -> bool:
    """Does the email write this date in a form that can be read as it: day and month in either
    order with or without a year ("15/02", "02/15/2027", "15.02.2027"), ISO, or "15 Feb"."""
    try:
        year, month, day = (int(x) for x in str(iso).split("-"))
    except ValueError:
        return False
    if str(iso) in text:
        return True
    for first, second, written_year, year_first in _numeric_dates(text):
        if {first, second} == {month, day} and (written_year == year or year_first and (first, second) == (month, day)):
            return True
    for match in _PARTIAL_DATE.finditer(text):
        if {int(match.group(1)), int(match.group(3))} == {month, day}:
            return True
    name = _MONTHS[month - 1]
    return re.search(rf"\b{day}(?:st|nd|rd|th)?\s+{name}|\b{name}[a-z]*\.?\s+{day}\b", text, re.IGNORECASE) is not None


def date_readings(iso: str) -> list[str]:
    """The date and, if its day and month can swap, the other reading."""
    year, month, day = (int(x) for x in str(iso).split("-"))
    readings = [f"{year:04d}-{month:02d}-{day:02d}"]
    if day != month and day <= 12:
        readings.append(f"{year:04d}-{day:02d}-{month:02d}")
    return readings


def resolve_delivery_date(extraction: POExtraction, text: str) -> list[str]:
    """Re-read an ambiguous numeric delivery date with the email's convention. Returns notes;
    one that stays ambiguous is listed in extraction.ambiguous_dates, which review flags."""
    value = extraction.delivery_date.value
    extraction.ambiguous_dates = []
    if not value:
        return []
    convention = date_convention(text, extraction.destination_country.value)
    resolved, ambiguous = resolve_date(str(value), text, convention)
    if ambiguous:
        extraction.ambiguous_dates = ["delivery_date"]
        return [f"Delivery date {value} is written as an ambiguous numeric date; flagged for review."]
    if resolved != str(value):
        extraction.delivery_date.value = date.fromisoformat(resolved)
        return [f"Delivery date read as {resolved} ({convention}), not {value}."]
    return []


def to_decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(parse_amount(value)))
    except (InvalidOperation, TypeError):
        return None
