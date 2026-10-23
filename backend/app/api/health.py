from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.llm.router import LLMRouter, get_router
from app.models import Email
from app.services.demo import read_snapshot

router = APIRouter(tags=["health"])


def _demo_loaded(session: Session) -> bool:
    """True when every email of the demo snapshot is in the database."""
    snapshot = read_snapshot()
    if snapshot is None:
        return False
    wanted = {row["external_id"] for row in snapshot["tables"].get("emails", [])}
    found = session.scalar(select(func.count()).select_from(Email).where(Email.external_id.in_(wanted)))
    return bool(wanted) and found == len(wanted)


@router.get("/health")
def health(session: Session = Depends(get_session), llm: LLMRouter = Depends(get_router)) -> dict[str, object]:
    settings = get_settings()
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"

    demo_loaded = database == "ok" and _demo_loaded(session)
    spent = llm.spent_today() if database == "ok" else None
    cap = settings.daily_spend_cap_usd
    # live: new emails get fresh model calls. cached: only stored responses are served.
    live = settings.llm_mode == "live" and bool(settings.nebius_api_key) and spent is not None and spent < cap
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "demo_loaded": demo_loaded,
        "mode": "live" if live else "cached",
        "spend_today_usd": f"{spent:.4f}" if spent is not None else None,
        "spend_cap_usd": str(cap),
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "nebius_configured": bool(settings.nebius_api_key),
        "tavily_configured": bool(settings.tavily_api_key),
    }
