from fastapi import APIRouter

from app.api import (
    attendance,
    auth,
    events,
    groups,
    guests,
    rating,
    results,
    signups,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(events.router)
api_router.include_router(groups.router)
api_router.include_router(signups.router)
api_router.include_router(attendance.router)
api_router.include_router(results.router)
api_router.include_router(rating.router)
api_router.include_router(guests.router)
