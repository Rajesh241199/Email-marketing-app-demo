from fastapi import APIRouter
from api.v1.endpoints import (
    auth, account, sender,
    subscribers, lists, tags, custom_fields, import_jobs,
    templates, preferences,
    campaigns, automation,
)

api_router = APIRouter()

# ── Rajesh ─────────────────────────────────────────────────────────────────
api_router.include_router(auth.router,      prefix="/auth",      tags=["Auth"])
api_router.include_router(account.router,   prefix="/account",   tags=["Account"])
api_router.include_router(sender.router,    prefix="/senders",   tags=["Senders"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
api_router.include_router(automation.router,prefix="/automations",tags=["Automation"])

# ── Heet ────────────────────────────────────────────────────────────────────
api_router.include_router(subscribers.router,   prefix="/subscribers",   tags=["Subscribers"])
api_router.include_router(lists.router,         prefix="/lists",         tags=["Lists"])
api_router.include_router(tags.router,          prefix="/tags",          tags=["Tags"])
api_router.include_router(custom_fields.router, prefix="/custom-fields", tags=["Custom Fields"])
api_router.include_router(import_jobs.router,   prefix="/import-jobs",   tags=["CSV Import"])
api_router.include_router(templates.router,     prefix="/templates",     tags=["Templates"])
api_router.include_router(preferences.router,   prefix="/preferences",   tags=["Preferences & Unsubscribe"])
