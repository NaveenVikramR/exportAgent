import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import Settings
from app.db import Base


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
    )
