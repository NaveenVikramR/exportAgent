import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import Settings
from app.db import Base
from app.services import tavily_client


@pytest.fixture(autouse=True)
def no_real_web_search(monkeypatch):
    """Tests never call Tavily; a test that needs search results passes its own fake."""
    def refuse(*_args, **_kwargs):
        raise AssertionError("A test tried to call the real Tavily API")

    monkeypatch.setattr(tavily_client, "search", refuse)


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        nebius_api_key="test-key",
        nebius_model_nano="test/nano",
        nebius_model_super="test/super",
        nebius_model_ultra="test/ultra",
        llm_force_tier=None,
        llm_task_tier_overrides={},
        llm_mode="live",
        llm_cache_enabled=True,
        daily_spend_cap_usd="1.00",
        rate_limit_per_minute=10,
        review_confidence_threshold=0.7,
    )
