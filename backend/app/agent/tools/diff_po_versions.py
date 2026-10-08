"""PO snapshots and the diff between two versions. Pure Python: no I/O, no LLM.

A snapshot is the plain-JSON form of a PO: the scalar fields plus line items
(colour, sizes, quantity, unit_price). Dates are ISO strings and prices are
decimal strings, so snapshots can be stored as they are.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from app.schemas.extraction import SCALAR_FIELDS, POExtraction
from app.schemas.orders import DELIVERY_PULLED_FORWARD, Change, ChangeKind, StatedChange

Snapshot = dict[str, Any]

_FIELD_KINDS: dict[str, ChangeKind] = {
    "total_quantity": "quantity",
    "unit_price": "price",
    "currency": "price",
    "delivery_date": "delivery_date",
    "incoterms": "incoterms",
    "port": "incoterms",
}
# The matching key; a different PO number is a different order, not a change.
_NOT_DIFFED = {"po_number"}


def snapshot_from_extraction(extraction: POExtraction) -> Snapshot:
    data = extraction.model_dump(mode="json")
    snapshot: Snapshot = {name: data[name]["value"] for name in SCALAR_FIELDS}
    snapshot["line_items"] = data["line_items"]
    return snapshot


def confidence_from_extraction(extraction: POExtraction) -> dict[str, float]:
    return {name: getattr(extraction, name).confidence for name in SCALAR_FIELDS}


def merge_snapshots(previous: Snapshot, update: Snapshot) -> Snapshot:
    """The order after an update: stated values replace old ones, unstated ones carry over.

    A delivery-change email names only the date; everything else stays as it was.
    """
    merged = deepcopy(previous)
    for name in SCALAR_FIELDS:
        if update.get(name) is not None:
            merged[name] = update[name]
    if update.get("line_items"):
        merged["line_items"] = deepcopy(update["line_items"])
    return merged


def _coerce(field: str, value: Any) -> Any:
    """A stated value in snapshot form, or None if it does not parse."""
    if value is None:
        return None
    try:
        if field == "delivery_date":
            return date.fromisoformat(str(value)).isoformat()
        if field == "unit_price":
            return str(Decimal(str(value)))
        if field == "total_quantity":
            return int(str(value).replace(",", ""))
    except (ValueError, InvalidOperation):
        return None
    return str(value).strip() or None


def apply_stated_changes(current: Snapshot, stated: list[StatedChange]) -> Snapshot:
    """Rebuild the earlier version of an order from the old values an email quotes."""
    baseline = deepcopy(current)
    for change in stated:
        old = _coerce(change.field, change.old)
        if old is not None:
            baseline[change.field] = old
    return baseline


def _same(field: str, old: Any, new: Any) -> bool:
    if field == "unit_price":
        try:
            return Decimal(str(old)) == Decimal(str(new))
        except InvalidOperation:
            return False
    if isinstance(old, str) and isinstance(new, str):
        return old.strip().casefold() == new.strip().casefold()
    return old == new


def _quantity_detail(label: str, old: int | None, new: int) -> str:
    if old is None:
        return f"{label} now stated: {new:,} pcs."
    delta = new - old
    pct = f" ({delta / old:+.1%})" if old else ""
    return f"{label} {old:,} → {new:,} pcs, {delta:+,}{pct}."


def _scalar_change(field: str, old: Any, new: Any) -> Change:
    kind = _FIELD_KINDS.get(field, "other")
    label = field.replace("_", " ").capitalize()
    if field == "total_quantity":
        return Change(field=field, kind=kind, old=old, new=new, detail=_quantity_detail("Total quantity", old, new))
    if field == "delivery_date" and old is not None:
        days = (date.fromisoformat(new) - date.fromisoformat(old)).days
        if days < 0:
            return Change(
                field=field, kind=kind, old=old, new=new, alert=DELIVERY_PULLED_FORWARD,
                detail=f"Delivery pulled forward by {-days} days ({old} → {new}): less production time.",
            )
        return Change(field=field, kind=kind, old=old, new=new, detail=f"Delivery pushed back by {days} days ({old} → {new}).")
    if old is None:
        return Change(field=field, kind=kind, old=old, new=new, detail=f"{label} now stated: {new}.")
    return Change(field=field, kind=kind, old=old, new=new, detail=f"{label} {old} → {new}.")


def _ratio(sizes: dict[str, int]) -> dict[str, Fraction] | None:
    total = sum(sizes.values())
    return {size: Fraction(qty, total) for size, qty in sizes.items()} if total else None


def _line_item_changes(old_items: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[Change]:
    old_by_colour = {(item.get("colour") or "").casefold(): item for item in old_items}
    new_by_colour = {(item.get("colour") or "").casefold(): item for item in new_items}
    changes: list[Change] = []

    for key, new in new_by_colour.items():
        colour = new.get("colour")
        old = old_by_colour.get(key)
        if old is None:
            changes.append(
                Change(field=f"line_items.{colour}", kind="colour", old=None, new=new.get("quantity"),
                       detail=f"Colour added: {colour}, {new.get('quantity') or 0:,} pcs.")
            )
            continue
        if new.get("quantity") is not None and old.get("quantity") != new["quantity"]:
            changes.append(
                Change(field=f"line_items.{colour}.quantity", kind="quantity",
                       old=old.get("quantity"), new=new["quantity"],
                       detail=_quantity_detail(colour, old.get("quantity"), new["quantity"]))
            )
        if new.get("unit_price") is not None and old.get("unit_price") is not None \
                and not _same("unit_price", old["unit_price"], new["unit_price"]):
            changes.append(
                Change(field=f"line_items.{colour}.unit_price", kind="price",
                       old=old["unit_price"], new=new["unit_price"],
                       detail=f"{colour} unit price {old['unit_price']} → {new['unit_price']}.")
            )
        # A breakdown that is only now stated is new information, not a ratio change.
        old_sizes, new_sizes = old.get("sizes") or {}, new.get("sizes") or {}
        if old_sizes and new_sizes and _ratio(old_sizes) != _ratio(new_sizes):
            changes.append(
                Change(field=f"line_items.{colour}.sizes", kind="size_ratio", old=old_sizes, new=new_sizes,
                       detail=f"{colour} size ratio changed.")
            )

    for key, old in old_by_colour.items():
        if key not in new_by_colour:
            colour = old.get("colour")
            changes.append(
                Change(field=f"line_items.{colour}", kind="colour", old=old.get("quantity"), new=None,
                       detail=f"Colour removed: {colour}, was {old.get('quantity') or 0:,} pcs.")
            )
    return changes


def diff_po_versions(old: Snapshot, new: Snapshot) -> list[Change]:
    """Every difference between two versions of the same PO, with old and new values.

    A value missing from `new` is treated as unchanged, not as removed. Size
    breakdowns are compared as ratios, so scaling a colour up keeps its ratio.
    """
    changes: list[Change] = []
    for field in SCALAR_FIELDS:
        if field in _NOT_DIFFED:
            continue
        old_value, new_value = old.get(field), new.get(field)
        if new_value is None or (old_value is not None and _same(field, old_value, new_value)):
            continue
        changes.append(_scalar_change(field, old_value, new_value))
    if new.get("line_items"):
        changes += _line_item_changes(old.get("line_items") or [], new["line_items"])
    return changes


@dataclass(frozen=True)
class PlannedVersion:
    data: Snapshot
    changes: list[Change]
    # document: values from the email or its PO; thread_reference: earlier values the email quotes
    basis: str
    from_email: bool


def plan_versions(
    previous: Snapshot | None, update: Snapshot, stated: list[StatedChange]
) -> list[PlannedVersion]:
    """The versions to append to an order when an email brings `update`.

    - New order: one version. If the email quotes earlier values (a reply thread
      about an order not yet in the store), the earlier version is rebuilt from
      them first, so the change is visible.
    - Existing order: stated values merged over the latest version, with the
      diff. Nothing changed, nothing to append.
    """
    if previous is None:
        if stated:
            baseline = apply_stated_changes(update, stated)
            return [
                PlannedVersion(baseline, [], "thread_reference", from_email=False),
                PlannedVersion(update, diff_po_versions(baseline, update), "document", from_email=True),
            ]
        return [PlannedVersion(update, [], "document", from_email=True)]
    merged = merge_snapshots(previous, update)
    changes = diff_po_versions(previous, merged)
    return [PlannedVersion(merged, changes, "document", from_email=True)] if changes else []
