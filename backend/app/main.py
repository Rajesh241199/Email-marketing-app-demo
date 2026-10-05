"""FastAPI application entrypoint. Routers are registered here as each domain lands."""

from __future__ import annotations

from fastapi import FastAPI

# Ensures every model is imported (and relationship() string references resolvable)
# before any query runs, regardless of which routers below are wired in.
import app.db.models  # noqa: F401
from app.accounts.router import router as accounts_router
from app.analytics.router import router as analytics_router
from app.auth.router import router as auth_router
from app.automations.router import router as automations_router
from app.campaigns.router import router as campaigns_router
from app.events.router import router as events_router
from app.imports.router import router as imports_router
from app.preferences.router import router as preferences_router
from app.segments.router import router as segments_router
from app.senders.router import router as senders_router
from app.subscribers.router import router as subscribers_router
from app.templates.router import content_blocks_router, media_router
from app.templates.router import router as templates_router

app = FastAPI(title="Email Marketing Platform API", version="0.1.0")

app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(senders_router)
app.include_router(subscribers_router)
app.include_router(segments_router)
app.include_router(templates_router)
app.include_router(content_blocks_router)
app.include_router(media_router)
app.include_router(imports_router)
app.include_router(campaigns_router)
app.include_router(preferences_router)
app.include_router(automations_router)
app.include_router(events_router)
app.include_router(analytics_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
