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


class FactoryProfile(BaseModel):
    id: str
    factory: str
    city: str
    country: str
    export_currency: str
    default_port: str
    ports: list[str]
    incoterms: list[str]
    capacity: Capacity
    lead_times: LeadTimes
    thresholds: Thresholds


@lru_cache
def load_profile(profile_id: str) -> FactoryProfile:
    path = PROFILES_DIR / f"{profile_id}.yaml"
    if not path.exists():
        raise ValueError(f"Unknown factory profile {profile_id!r}; expected {path}")
    return FactoryProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def list_profiles() -> list[FactoryProfile]:
    return [load_profile(path.stem) for path in sorted(PROFILES_DIR.glob("*.yaml"))]
