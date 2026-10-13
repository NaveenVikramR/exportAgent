"""Factory/country profiles: list them, compare an order across them, and switch an order's profile.

The comparison is Python only (no model call): the same feasibility check the risk agent
uses, run under each profile's capacity and lead times, plus the invoice header each
profile prints. Switching changes which profile new documents and risk runs use.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.tools.agent_tools import ToolContext, run_tool
from app.db import get_session
from app.models import Email, Order
from app.services.profiles import PROFILES_DIR, FactoryProfile, load_profile

router = APIRouter(tags=["profiles"])


def profile_ids() -> list[str]:
    return sorted(path.stem for path in PROFILES_DIR.glob("*.yaml"))


def profile_info(profile: FactoryProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "factory": profile.factory,
        "city": profile.city,
        "country": profile.country,
        "default_port": profile.default_port,
        "pcs_per_week": profile.capacity.pcs_per_week,
        "free_pcs_per_week": round(profile.capacity.pcs_per_week * (1 - profile.capacity.baseline_utilisation)),
        "fabric_days": profile.lead_times.fabric_days,
    }


def invoice_header(profile: FactoryProfile) -> dict[str, Any]:
    docs = profile.documents
    return {
        "exporter_name": docs.exporter.name,
        "exporter_address": docs.exporter.address,
        "invoice_title": docs.format.invoice_title,
        "country_of_origin": docs.format.country_of_origin,
        "invoice_prefix": docs.invoice_prefix,
        "port_of_loading": profile.default_port,
        "registration": {name: docs.registration.get(name, "TO BE CONFIRMED") for name in docs.format.registration_fields},
        "declarations": docs.format.declarations,
    }


@router.get("/profiles")
def list_profiles() -> list[dict[str, Any]]:
    return [profile_info(load_profile(pid)) for pid in profile_ids()]


def _order_or_404(session: Session, order_id: int) -> Order:
    order = session.get(Order, order_id)
    if order is None or not order.versions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return order


def _as_of(session: Session, order: Order) -> date:
    """The date of the email behind the latest version: feasibility as the factory saw it then."""
    latest = order.versions[-1]
    email = session.get(Email, latest.email_id) if latest.email_id else None
    return (email.received_at if email else latest.created_at).date()


@router.get("/orders/{order_id}/profiles")
def compare(order_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    order = _order_or_404(session, order_id)
    data = order.versions[-1].data
    rows = []
    for pid in profile_ids():
        profile = load_profile(pid)
        feasibility = None
        if data.get("delivery_date") and data.get("total_quantity"):
            ctx = ToolContext(session=session, as_of=_as_of(session, order), profile=profile)
            _args, output, _summary = run_tool(ctx, "check_delivery_feasibility", f'{{"order_id": {order.id}}}')
            if "verdict" in output:
                feasibility = {
                    "verdict": output["verdict"],
                    "reason": output["reason"],
                    "utilisation": output.get("utilisation"),
                    "slack_days": output.get("slack_days"),
                    "shortfall": output.get("shortfall_pcs"),
                }
        rows.append({"profile": profile_info(profile), "feasibility": feasibility, "invoice": invoice_header(profile)})
    return rows


class ProfileChange(BaseModel):
    profile: str


@router.patch("/orders/{order_id}/profile")
def switch(order_id: int, payload: ProfileChange, session: Session = Depends(get_session)) -> dict[str, str]:
    """New documents and risk assessments for this order use the chosen profile."""
    if payload.profile not in profile_ids():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown profile.")
    order = _order_or_404(session, order_id)
    order.profile = payload.profile
    session.commit()
    return {"profile": order.profile}
