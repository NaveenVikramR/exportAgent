"""The tools the risk agent can call. The model picks tools; these functions do all the maths.

Each tool returns (result, summary): the JSON the model sees and one line for
the trace panel. Failures come back as {"error": ...} so the model can adapt.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tools.diff_po_versions import diff_po_versions
from app.agent.tools.feasibility import check_feasibility
from app.models import Email, Order
from app.services import tavily_client
from app.services.orders import find_order as find_order_by_po
from app.services.profiles import FactoryProfile
from app.services.research import cached_search


@dataclass
class ToolContext:
    session: Session
    as_of: date
    profile: FactoryProfile
    search: Callable[..., tavily_client.SearchResponse] = tavily_client.search
    # tool name -> number of calls, to stop runaway web searches
    calls: dict[str, int] = field(default_factory=dict)


_MAX_SEARCHES_PER_TOOL = 2


def _spec(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


TOOL_SPECS: list[dict[str, Any]] = [
    _spec(
        "find_order",
        "Look up an order by PO number: buyer, every stored version with its delivery date, "
        "quantity and price, the alerts on each version, and how many earlier orders the buyer has.",
        {"po_number": {"type": "string"}},
        ["po_number"],
    ),
    _spec(
        "diff_po_versions",
        "Compare two stored versions of an order. Returns each change with old and new values "
        "and alerts such as delivery_pulled_forward.",
        {
            "order_id": {"type": "integer"},
            "from_version": {"type": "integer"},
            "to_version": {"type": "integer"},
        },
        ["order_id", "from_version", "to_version"],
    ),
    _spec(
        "check_delivery_feasibility",
        "Check whether the factory can produce the order by a delivery date, using factory capacity, "
        "fabric lead time and other orders due in the same window. Defaults to the order's current "
        "date and quantity; pass delivery_date or quantity to test another plan (for example the "
        "previous date). Set fabric_ready only if the email says fabric is already in-house.",
        {
            "order_id": {"type": "integer"},
            "delivery_date": {"type": "string", "description": "YYYY-MM-DD"},
            "quantity": {"type": "integer"},
            "fabric_ready": {"type": "boolean"},
        },
        ["order_id"],
    ),
    _spec(
        "check_compliance",
        "Web search (Tavily) for import, labelling and product-safety requirements for apparel "
        "shipped to a country. Returns a summary and source URLs.",
        {
            "destination_country": {"type": "string"},
            "product": {"type": "string", "description": "the garment as described in the email, e.g. its fibre and type"},
        },
        ["destination_country", "product"],
    ),
    _spec(
        "lookup_buyer",
        "Web search (Tavily) for background on a buyer company. Returns a summary and source URLs.",
        {"company_name": {"type": "string"}, "country": {"type": "string"}},
        ["company_name"],
    ),
]


def _order_or_error(ctx: ToolContext, order_id: Any) -> Order:
    order = ctx.session.get(Order, int(order_id)) if str(order_id).isdigit() else None
    if order is None:
        raise ValueError(f"No order with id {order_id}.")
    return order


def _find_order(ctx: ToolContext, po_number: str) -> tuple[dict, str]:
    order = find_order_by_po(ctx.session, po_number)
    if order is None:
        return {"found": False, "po_number": po_number}, f"No order found for PO {po_number}."
    earlier = ctx.session.scalars(
        select(Order).where(Order.buyer == order.buyer, Order.id != order.id)
    ).all()
    versions = [
        {
            "version": v.version,
            "basis": v.basis,
            "delivery_date": v.data.get("delivery_date"),
            "total_quantity": v.data.get("total_quantity"),
            "unit_price": v.data.get("unit_price"),
            "currency": v.data.get("currency"),
            "destination_country": v.data.get("destination_country"),
            "change_count": len(v.changes or []),
            "alerts": sorted({c["alert"] for c in v.changes or [] if c.get("alert")}),
        }
        for v in order.versions
    ]
    latest = versions[-1]
    result = {
        "found": True,
        "order_id": order.id,
        "buyer": order.buyer,
        "po_number": order.po_number,
        "style": order.style,
        "current_version": order.current_version,
        "versions": versions,
        "earlier_orders_from_buyer": len(earlier),
    }
    summary = (
        f"PO {order.po_number}: v{order.current_version}, {latest['total_quantity'] or '?'} pcs, "
        f"delivery {latest['delivery_date'] or '?'}"
        + (f", alerts {', '.join(latest['alerts'])}" if latest["alerts"] else "")
    )
    return result, summary


def _diff(ctx: ToolContext, order_id: Any, from_version: int, to_version: int) -> tuple[dict, str]:
    order = _order_or_error(ctx, order_id)
    by_number = {v.version: v for v in order.versions}
    if from_version not in by_number or to_version not in by_number:
        raise ValueError(f"Order {order.id} has versions {sorted(by_number)}.")
    changes = diff_po_versions(by_number[from_version].data, by_number[to_version].data)
    result = {
        "order_id": order.id,
        "from_version": from_version,
        "to_version": to_version,
        "changes": [change.model_dump(mode="json") for change in changes],
        "alerts": sorted({c.alert for c in changes if c.alert}),
    }
    summary = f"v{from_version} → v{to_version}: {len(changes)} changes" + (
        f" ({', '.join(result['alerts'])})" if result["alerts"] else ""
    )
    return result, summary


def _other_orders_load(ctx: ToolContext, order: Order, delivery: date) -> tuple[int, list[dict]]:
    """Other orders known on the as-of date and due by `delivery`: they compete for the same capacity."""
    known_by = datetime.combine(ctx.as_of + timedelta(days=1), time(), tzinfo=UTC)
    order_ids = set(
        ctx.session.scalars(
            select(Email.order_id).where(
                Email.order_id.is_not(None), Email.order_id != order.id, Email.received_at < known_by
            )
        )
    )
    load, contributing = 0, []
    for other in ctx.session.scalars(select(Order).where(Order.id.in_(order_ids))):
        data = other.versions[-1].data if other.versions else {}
        due, qty = data.get("delivery_date"), data.get("total_quantity")
        if due and qty and ctx.as_of < date.fromisoformat(due) <= delivery:
            load += int(qty)
            contributing.append({"po_number": other.po_number, "delivery_date": due, "quantity": qty})
    return load, contributing


def _feasibility(
    ctx: ToolContext,
    order_id: Any,
    delivery_date: str | None = None,
    quantity: int | None = None,
    fabric_ready: bool = False,
) -> tuple[dict, str]:
    order = _order_or_error(ctx, order_id)
    current = order.versions[-1].data
    if not (delivery_date or current.get("delivery_date")):
        raise ValueError("The order has no delivery date yet; pass delivery_date.")
    target = date.fromisoformat(delivery_date or current["delivery_date"])
    qty = int(quantity or current.get("total_quantity") or 0)
    if qty <= 0:
        raise ValueError("The order has no quantity yet; pass quantity.")
    load, contributing = _other_orders_load(ctx, order, target)
    result = check_feasibility(
        quantity=qty, delivery_date=target, as_of=ctx.as_of, profile=ctx.profile,
        other_orders_load=load, fabric_ready=bool(fabric_ready),
    ).to_dict()
    result.update(
        order_id=order.id,
        profile=ctx.profile.id,
        other_orders=contributing,
        fabric_ready=bool(fabric_ready),
        is_current_plan=(target.isoformat() == current.get("delivery_date") and qty == current.get("total_quantity")),
    )
    return result, f"{result['verdict'].upper()} for {qty:,} pcs by {target.isoformat()}: {result['reason']}"


def _search_tool(ctx: ToolContext, name: str, query: str) -> tuple[dict, str]:
    ctx.calls[name] = ctx.calls.get(name, 0) + 1
    if ctx.calls[name] > _MAX_SEARCHES_PER_TOOL:
        raise ValueError(f"{name} already used {_MAX_SEARCHES_PER_TOOL} times in this run.")
    result = cached_search(ctx.session, query, search=ctx.search)
    summary = f"{len(result['sources'])} sources" + (" (cached)" if result.get("cached") else "") + f" for: {query}"
    return result, summary


def _compliance(ctx: ToolContext, destination_country: str, product: str) -> tuple[dict, str]:
    query = f"{product} import requirements {destination_country}: labelling, fibre composition, care labels, chemical restrictions"
    return _search_tool(ctx, "check_compliance", query)


def _buyer(ctx: ToolContext, company_name: str, country: str | None = None) -> tuple[dict, str]:
    query = f"{company_name} {country or ''} apparel company profile".strip()
    return _search_tool(ctx, "lookup_buyer", query)


_IMPLEMENTATIONS: dict[str, Callable[..., tuple[dict, str]]] = {
    "find_order": _find_order,
    "diff_po_versions": _diff,
    "check_delivery_feasibility": _feasibility,
    "check_compliance": _compliance,
    "lookup_buyer": _buyer,
}


def run_tool(ctx: ToolContext, name: str, arguments: str) -> tuple[dict, dict, str]:
    """Returns (parsed arguments, result, summary). Never raises."""
    try:
        args = json.loads(arguments or "{}")
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        return {}, {"error": f"Invalid arguments: {exc}"}, f"error: invalid arguments for {name}"
    implementation = _IMPLEMENTATIONS.get(name)
    if implementation is None:
        return args, {"error": f"Unknown tool {name}."}, f"error: unknown tool {name}"
    try:
        result, summary = implementation(ctx, **args)
    except (TypeError, ValueError, tavily_client.TavilyError) as exc:
        return args, {"error": str(exc)}, f"error: {exc}"
    return args, result, summary
