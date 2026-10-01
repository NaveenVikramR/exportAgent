from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, object]:
    settings = get_settings()
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "nebius_configured": bool(settings.nebius_api_key),
        "tavily_configured": bool(settings.tavily_api_key),
    }
