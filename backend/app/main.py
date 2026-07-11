import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from starlette.middleware.sessions import SessionMiddleware

from app.admin.auth import AdminAuth
from app.admin.moderation import router as moderation_router
from app.admin.tools_dashboard import router as tools_dashboard_router
from app.admin.tools_events import router as tools_events_router
from app.admin.tools_groups import router as tools_groups_router
from app.admin.tools_guests import router as tools_guests_router
from app.admin.tools_results import router as tools_results_router
from app.admin.views import ALL_VIEWS
from app.api.router import api_router
from app.core.bootstrap import ensure_initial_admin
from app.core.config import settings
from app.core.db import engine

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    os.makedirs(settings.media_root, exist_ok=True)
    await ensure_initial_admin()
    yield


app = FastAPI(title="DH Running Community API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session cookie shared with SQLAdmin's auth so the custom /admin-tools pages can
# read the admin login session. https_only tracks settings.secure_cookies, not
# environment — see its docstring in config.py for why those are different.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.admin_secret_key,
    https_only=settings.secure_cookies,
)

app.include_router(api_router)
# Custom admin-tools pages (registered before SQLAdmin so their paths resolve).
# Reachable by organizer + admin; some sub-areas (CSV import/moderation, results
# approval) are further restricted to admin only inside each router.
app.include_router(tools_dashboard_router)
app.include_router(tools_events_router)
app.include_router(tools_groups_router)
app.include_router(tools_results_router)
app.include_router(tools_guests_router)
app.include_router(moderation_router)

# Serve uploaded media in dev (in prod nginx serves /media directly).
os.makedirs(settings.media_root, exist_ok=True)
app.mount(settings.media_url, StaticFiles(directory=settings.media_root), name="media")

# SQLAdmin panel (admin role only).
admin = Admin(app, engine, authentication_backend=AdminAuth(secret_key=settings.admin_secret_key))
for view in ALL_VIEWS:
    admin.add_view(view)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
