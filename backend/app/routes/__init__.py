from fastapi import APIRouter

from app.routes import (
    admin,
    ai,
    auth,
    health,
    incidents,
    reports,
    tracking,
    voice,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
api_router.include_router(tracking.router, prefix="/tracking", tags=["tracking"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
