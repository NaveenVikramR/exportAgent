"""Commercial Invoice and Packing List content, computed in Python. No model is involved.

Every number comes from the order's latest PO version, the factory profile and the
style catalogue (backend/catalog/styles.yaml). A value we do not have is never
guessed: it is reported as TO BE CONFIRMED, and listed in `tbc_fields`.

Money: line amount = quantity x unit price, rounded half-up to the currency's minor
unit; the invoice total is the sum of the rounded line amounts.
Weights: kg rounded half-up to 2 decimals per carton row; totals are the sum of rows.
"""

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Any

import yaml

from app.config import BACKEND_DIR
from app.services.profiles import FactoryProfile

TBC = "TO BE CONFIRMED"
CATALOG_PATH = BACKEND_DIR / "catalog" / "styles.yaml"

# ISO 4217 minor units for the currencies the demo sees
MINOR_UNITS = {"USD": 2, "EUR": 2, "GBP": 2, "AUD": 2, "CAD": 2, "INR": 2, "BDT": 2, "JPY": 0}
CURRENCY_WORDS = {
    "USD": ("US Dollars", "Cents"),
    "EUR": ("Euros", "Cents"),
    "GBP": ("Pounds Sterling", "Pence"),
    "AUD": ("Australian Dollars", "Cents"),
    "CAD": ("Canadian Dollars", "Cents"),
    "JPY": ("Japanese Yen", None),
}
# For these Incoterms the named place is where the goods are loaded; for the others it is the destination.
_ORIGIN_TERMS = {"EXW", "FCA", "FAS", "FOB"}
_KG = Decimal("0.01")
_CBM = Decimal("0.001")


@lru_cache
def load_catalog() -> dict[str, dict[str, Any]]:
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}


def round_money(amount: Decimal, currency: str) -> Decimal:
    exponent = Decimal(1).scaleb(-MINOR_UNITS.get(currency, 2))
    return amount.quantize(exponent, rounding=ROUND_HALF_UP)


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven",
         "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _words_below_thousand(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(f"{_ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        parts.append(_TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        parts.append(_ONES[n])
    return " ".join(parts)


def number_in_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for value, name in ((10**9, "Billion"), (10**6, "Million"), (10**3, "Thousand"), (1, "")):
        if n >= value:
            parts.append(f"{_words_below_thousand(n // value)} {name}".strip())
            n %= value
    return " ".join(parts)


def amount_in_words(amount: Decimal, currency: str) -> str:
    major_name, minor_name = CURRENCY_WORDS.get(currency, (currency, "Cents"))
    whole = int(amount)
    minor = int((amount - whole) * (10 ** MINOR_UNITS.get(currency, 2)))
    text = f"{major_name} {number_in_words(whole)}"
    if minor and minor_name:
        text += f" and {minor_name} {number_in_words(minor)}"
    return f"{text} Only"


def _decimal(value: Any) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


@dataclass
class InvoiceLine:
    description: str
    colour: str
    hs_code: str
    quantity: int
    unit_price: Decimal | None
    amount: Decimal | None


@dataclass
class Invoice:
    title: str
    number: str
    date: str
    exporter_name: str
    exporter_address: str
    registration: list[tuple[str, str]]
    buyer: str
    consignee: str
    notify_party: str
    po_number: str
    style: str
    currency: str
    incoterm: str
    named_place: str
    port_of_loading: str
    port_of_discharge: str
    final_destination: str
    country_of_origin: str
    payment_terms: str
    lines: list[InvoiceLine]
    total_quantity: int
    total_amount: Decimal | None
    amount_in_words: str
    declarations: list[str]
    bank: list[tuple[str, str]]
    tbc_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CartonRow:
    carton_from: int
    carton_to: int
    colour: str
    size: str
    pcs_per_carton: int
    cartons: int
    quantity: int
    net_kg: Decimal | None
    gross_kg: Decimal | None


@dataclass
class PackingList:
    number: str
    date: str
    invoice_number: str
    exporter_name: str
    exporter_address: str
    buyer: str
    po_number: str
    style: str
    description: str
    rows: list[CartonRow]
    total_cartons: int
    total_quantity: int
    total_net_kg: Decimal | None
    total_gross_kg: Decimal | None
    carton_dimensions_cm: str
    total_cbm: Decimal | None
    notes: list[str] = field(default_factory=list)
    tbc_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class _Missing:
    """Collects the fields that print as TO BE CONFIRMED."""

    def __init__(self) -> None:
        self.fields: list[str] = []

    def __call__(self, label: str, value: Any) -> str:
        if value in (None, ""):
            if label not in self.fields:
                self.fields.append(label)
            return TBC
        return str(value)


def _style(data: dict) -> dict[str, Any]:
    return load_catalog().get(data.get("style") or "", {})


def _quantities(data: dict) -> list[dict]:
    """Line items with a quantity; a single line for the whole order if there are none."""
    items = [item for item in data.get("line_items") or [] if item.get("quantity") or item.get("sizes")]
    if items:
        return items
    return [{"colour": None, "sizes": {}, "quantity": data.get("total_quantity"), "unit_price": None}]


def _ports(data: dict, profile: FactoryProfile) -> tuple[str | None, str | None, str | None]:
    """(incoterm, port of loading, port of discharge) from the PO's Incoterm and its named place."""
    incoterm = (data.get("incoterms") or "").upper() or None
    named = data.get("port")
    if incoterm in _ORIGIN_TERMS:
        return incoterm, named or profile.default_port, None
    return incoterm, profile.default_port, named


def document_number(prefix: str, order_id: int, version: int, on: date) -> str:
    return f"{prefix}{on.year}/{order_id:04d}-{version}"


def build_invoice(order: Any, data: dict, version: int, profile: FactoryProfile, on: date) -> Invoice:
    docs = profile.documents
    tbc = _Missing()
    style = _style(data)
    currency = (data.get("currency") or profile.export_currency).upper()
    order_price = _decimal(data.get("unit_price"))

    lines: list[InvoiceLine] = []
    for item in _quantities(data):
        quantity = int(item.get("quantity") or sum((item.get("sizes") or {}).values()) or 0)
        price = _decimal(item.get("unit_price")) or order_price
        lines.append(InvoiceLine(
            description=tbc("Goods description", style.get("description")),
            colour=item.get("colour") or "As per PO",
            hs_code=tbc("HS code", style.get("hs_code")),
            quantity=quantity,
            unit_price=price,
            amount=round_money(quantity * price, currency) if price is not None else None,
        ))
    if any(line.unit_price is None for line in lines):
        tbc("Unit price", None)
    total = (
        sum((line.amount for line in lines), Decimal(0)) if all(line.amount is not None for line in lines) else None
    )

    incoterm, loading, discharge = _ports(data, profile)
    return Invoice(
        title=docs.format.invoice_title,
        number=document_number(docs.invoice_prefix, order.id, version, on),
        date=on.isoformat(),
        exporter_name=docs.exporter.name,
        exporter_address=docs.exporter.address,
        registration=[(name, tbc(name, docs.registration.get(name))) for name in docs.format.registration_fields],
        buyer=tbc("Buyer", data.get("buyer") or order.buyer),
        consignee=tbc("Consignee name and address", None),
        notify_party=tbc("Notify party", None),
        po_number=order.po_number,
        style=tbc("Style", data.get("style")),
        currency=currency,
        incoterm=tbc("Incoterm", incoterm),
        named_place=tbc("Incoterm named place", data.get("port")),
        port_of_loading=tbc("Port of loading", loading),
        port_of_discharge=tbc("Port of discharge", discharge),
        final_destination=tbc("Final destination", data.get("destination_country")),
        country_of_origin=docs.format.country_of_origin,
        payment_terms=tbc("Payment terms", None),
        lines=lines,
        total_quantity=sum(line.quantity for line in lines),
        total_amount=total,
        amount_in_words=amount_in_words(total, currency) if total is not None else TBC,
        declarations=docs.format.declarations,
        bank=[(name, tbc(name, docs.bank.get(name))) for name in docs.bank_fields],
        tbc_fields=tbc.fields,
    )


def _carton_rows(colour: str, size: str, quantity: int, per_carton: int, start: int) -> list[tuple]:
    """Full cartons of one colour and size, then one carton with the remainder."""
    rows = []
    full, remainder = divmod(quantity, per_carton)
    if full:
        rows.append((start, start + full - 1, colour, size, per_carton, full, full * per_carton))
        start += full
    if remainder:
        rows.append((start, start, colour, size, remainder, 1, remainder))
    return rows


def build_packing_list(
    order: Any, data: dict, version: int, profile: FactoryProfile, on: date, invoice_number: str
) -> PackingList:
    docs = profile.documents
    tbc = _Missing()
    style = _style(data)
    per_carton = int(style.get("pcs_per_carton") or docs.packing.default_pcs_per_carton)
    weight = _decimal(style.get("net_weight_per_piece_kg"))
    tare = Decimal(str(docs.packing.carton_tare_kg))
    dimensions = style.get("carton_dimensions_cm")
    notes: list[str] = []
    if not style.get("pcs_per_carton"):
        notes.append(f"Pieces per carton: factory default of {per_carton}; confirm for this style.")

    raw_rows: list[tuple] = []
    carton = 1
    for item in _quantities(data):
        colour = item.get("colour") or "As per PO"
        sizes = {size: int(qty) for size, qty in (item.get("sizes") or {}).items() if qty}
        if not sizes:
            sizes = {"Assorted": int(item.get("quantity") or 0)}
            notes.append(f"{colour}: no size breakdown in the PO; packed as assorted sizes.")
        for size, quantity in sizes.items():
            new_rows = _carton_rows(colour, size, quantity, per_carton, carton)
            raw_rows += new_rows
            carton += sum(row[5] for row in new_rows)

    rows = []
    for start, end, colour, size, pcs, cartons, quantity in raw_rows:
        net = (quantity * weight).quantize(_KG, rounding=ROUND_HALF_UP) if weight is not None else None
        gross = (net + cartons * tare).quantize(_KG, rounding=ROUND_HALF_UP) if net is not None else None
        rows.append(CartonRow(start, end, colour, size, pcs, cartons, quantity, net, gross))
    if weight is None:
        tbc("Net weight per piece", None)

    total_cartons = sum(row.cartons for row in rows)
    cbm = None
    if dimensions:
        length, width, height = (Decimal(str(d)) for d in dimensions)
        cbm = (total_cartons * length * width * height / Decimal(1_000_000)).quantize(_CBM, rounding=ROUND_HALF_UP)
    return PackingList(
        number=document_number(docs.packing_prefix, order.id, version, on),
        date=on.isoformat(),
        invoice_number=invoice_number,
        exporter_name=docs.exporter.name,
        exporter_address=docs.exporter.address,
        buyer=tbc("Buyer", data.get("buyer") or order.buyer),
        po_number=order.po_number,
        style=tbc("Style", data.get("style")),
        description=tbc("Goods description", style.get("description")),
        rows=rows,
        total_cartons=total_cartons,
        total_quantity=sum(row.quantity for row in rows),
        total_net_kg=sum((r.net_kg for r in rows), Decimal(0)) if weight is not None else None,
        total_gross_kg=sum((r.gross_kg for r in rows), Decimal(0)) if weight is not None else None,
        carton_dimensions_cm=" x ".join(str(d) for d in dimensions) if dimensions else tbc("Carton dimensions", None),
        total_cbm=cbm,
        notes=notes,
        tbc_fields=tbc.fields,
    )
