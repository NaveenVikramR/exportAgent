"""Reset the public demo to its committed snapshot (only where DEMO_RESET_ENABLED is set)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.rate_limit import rate_limit
from app.config import get_settings
from app.db import get_session
from app.services.demo import load_snapshot, read_snapshot

router = APIRouter(tags=["demo"])


@router.post("/demo/reset", dependencies=[Depends(rate_limit)])
def reset(session: Session = Depends(get_session)) -> dict[str, int]:
    """Put the demo inbox back as it was: undo approvals, decisions and pasted emails."""
    if not get_settings().demo_reset_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo reset is not enabled here.")
    snapshot = read_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No demo snapshot is installed.")
    counts = load_snapshot(session, snapshot)
    return {"emails": counts.get("emails", 0)}
