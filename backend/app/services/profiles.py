"""Factory/country profiles, loaded from backend/profiles/<id>.yaml."""

from functools import lru_cache

import yaml
from pydantic import BaseModel

from app.config import BACKEND_DIR

PROFILES_DIR = BACKEND_DIR / "profiles"


class Capacity(BaseModel):
    pcs_per_week: int
    baseline_utilisation: float


class LeadTimes(BaseModel):
    fabric_days: int
    min_production_days: int


class Thresholds(BaseModel):
    tight_utilisation: float
    min_slack_days: int


class Exporter(BaseModel):
    name: str
    address: str


class DocumentFormat(BaseModel):
    invoice_title: str
    country_of_origin: str
    registration_fields: list[str]
    declarations: list[str]


class Packing(BaseModel):
    default_pcs_per_carton: int
    carton_tare_kg: float


class DocumentSettings(BaseModel):
    exporter: Exporter
    invoice_prefix: str
    packing_prefix: str
    format: DocumentFormat
    # values for format.registration_fields / bank_fields; anything missing prints as TO BE CONFIRMED
    registration: dict[str, str] = {}
    bank_fields: list[str] = []
    bank: dict[str, str] = {}
    packing: Packing


class FactoryProfile(BaseModel):
    id: str
    factory: str
    contact_name: str
    contact_role: str
    city: str
    country: str
    export_currency: str
    default_port: str
    ports: list[str]
    incoterms: list[str]
    capacity: Capacity
    lead_times: LeadTimes
    thresholds: Thresholds
    documents: DocumentSettings


@lru_cache
def load_profile(profile_id: str) -> FactoryProfile:
    path = PROFILES_DIR / f"{profile_id}.yaml"
    if not path.exists():
        raise ValueError(f"Unknown factory profile {profile_id!r}; expected {path}")
    return FactoryProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def list_profiles() -> list[FactoryProfile]:
    return [load_profile(path.stem) for path in sorted(PROFILES_DIR.glob("*.yaml"))]
