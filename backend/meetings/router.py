from fastapi import APIRouter

from backend.meetings.routes_admin import router as admin_router
from backend.meetings.routes_dashboard import router as dashboard_router
from backend.meetings.routes_room import router as room_router
from backend.meetings.routes_schedule import router as schedule_router
from backend.meetings.ws_signaling import router as ws_router

router = APIRouter()
router.include_router(schedule_router)
router.include_router(room_router)
router.include_router(dashboard_router)
router.include_router(admin_router)
router.include_router(ws_router)
