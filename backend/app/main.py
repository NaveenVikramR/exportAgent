from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, decisions, documents, drafts, emails, health, orders, trace
from app.config import get_settings

app = FastAPI(title="ExportAgent API", version="0.1.0")

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
