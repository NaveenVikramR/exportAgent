from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.llm.tasks import TaskType, Tier

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    nebius_api_key: str | None = None
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"

    nebius_model_nano: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    nebius_model_super: str = "nvidia/nemotron-3-super-120b-a12b"
    nebius_model_ultra: str = "nvidia/Nemotron-3-Ultra-550b-a55b"

    # USD per 1M tokens
    nebius_price_nano_input: Decimal = Decimal("0.06")
    nebius_price_nano_output: Decimal = Decimal("0.24")
    nebius_price_super_input: Decimal = Decimal("0.30")
    nebius_price_super_output: Decimal = Decimal("0.90")
    nebius_price_ultra_input: Decimal = Decimal("1.00")
    nebius_price_ultra_output: Decimal = Decimal("3.00")

    llm_force_tier: Tier | None = None
    llm_task_tier_overrides: dict[TaskType, Tier] = Field(default_factory=dict)
    llm_timeout_seconds: float = 60.0
    # live = call Token Factory; mock = rule-based stand-in, no network, no cost
    llm_mode: Literal["live", "mock"] = "live"
    llm_cache_enabled: bool = True
    # Live calls stop once today's (UTC) spend reaches this. Cached responses still serve.
    daily_spend_cap_usd: Decimal = Decimal("1.00")

    # Requests per IP per minute on endpoints that trigger LLM work
    rate_limit_per_minute: int = 10
    # Extracted fields below this confidence are flagged for human review
    review_confidence_threshold: float = 0.7

    tavily_api_key: str | None = None

    # Re-extract fields that fail a Python check with the stronger model (off = Nano-only baseline)
    escalation_enabled: bool = True
    # Run the deterministic order checks in Python before the agent loop (see app/agent/loop.py)
    agent_prefetch: bool = True

    # Factory/country profile new orders are processed under (profiles arrive in a later milestone)
    factory_profile: str = "india_tiruppur"

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'exportagent.db').as_posix()}"
    web_origin: str = "http://localhost:3000"

    def model_for(self, tier: Tier) -> str:
        return getattr(self, f"nebius_model_{tier.value}")

    def prices_for(self, tier: Tier) -> tuple[Decimal, Decimal]:
        """(input, output) price in USD per 1M tokens."""
        return (
            getattr(self, f"nebius_price_{tier.value}_input"),
            getattr(self, f"nebius_price_{tier.value}_output"),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
