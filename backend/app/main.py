from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from app.api import agent, dashboard, decisions, demo, documents, drafts, emails, health, matches, orders, profiles, trace
from app.config import get_settings
from app.db import SessionLocal
from app.services.demo import is_empty, load_snapshot, read_snapshot


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if get_settings().demo_seed_on_empty:
        with SessionLocal() as session:
            snapshot = read_snapshot()
            if snapshot is not None and is_empty(session):
                load_snapshot(session, snapshot)
    yield


app = FastAPI(title="ExportAgent API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(trace.router, prefix="/api")
app.include_router(emails.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(drafts.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(decisions.router, prefix="/api")
app.include_router(matches.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(profiles.router, prefix="/api")
app.include_router(demo.router, prefix="/api")
