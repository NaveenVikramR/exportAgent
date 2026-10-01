from decimal import Decimal
from functools import lru_cache
from pathlib import Path

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

    nebius_model_nano: str = "nvidia/nvidia-nemotron-3-nano-30b-a3b"
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

    tavily_api_key: str | None = None

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
