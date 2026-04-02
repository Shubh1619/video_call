from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from datetime import datetime, timezone
import os
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import json

from backend.auth.router import router as auth_router
from backend.meetings.router import router as meetings_router
from backend.scheduler.unified_scheduler import start_all_schedulers, shutdown_all_schedulers, get_scheduler_status
from backend.email.db import init_db, engine
from backend.notes.routes import router as notes_router
from backend.routers import stt as stt_router
from backend.services.stt_service import SttService
from backend.core.rate_limit import limiter
from backend.core.config import CORS_ORIGINS, REDIS_ENABLED, SCHEDULER_ENABLED

# WebSocket manager for signaling
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room: str):
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)

    def disconnect(self, websocket: WebSocket, room: str):
        if room in self.active_connections:
            self.active_connections[room].remove(websocket)
            if not self.active_connections[room]:
                del self.active_connections[room]

    async def broadcast(self, message: str, room: str, exclude: WebSocket = None):
        if room in self.active_connections:
            for connection in self.active_connections[room]:
                if connection != exclude:
                    try:
                        await connection.send_text(message)
                    except:
                        pass

manager = ConnectionManager()

app = FastAPI(title="AI Meeting Assistant - Secure Meeting")

# --- Rate Limiting Setup ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS ---
LOCAL_ORIGINS = {
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
}

DEPLOYED_ORIGINS = {
    "https://meet-frontend-4op.pages.dev",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(
        {
            *(origin.strip().rstrip("/") for origin in CORS_ORIGINS if origin.strip()),
            *LOCAL_ORIGINS,
            *DEPLOYED_ORIGINS,
        }
    ),
    # Allow Cloudflare Pages preview domains for this frontend project.
    allow_origin_regex=r"^https://meet-frontend-.*\.pages\.dev$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database ---
@app.on_event("startup")
async def on_startup():
    init_db()
    app.state.stt_service = SttService()
    if SCHEDULER_ENABLED:
        start_all_schedulers()
    else:
        print("Scheduler disabled on this instance (SCHEDULER_ENABLED=false)")
    print("✓ Application started successfully")

@app.on_event("shutdown")
async def on_shutdown():
    if SCHEDULER_ENABLED:
        shutdown_all_schedulers()
    print("✓ Application shutdown complete")

# --- Health Check Endpoint ---
@app.get("/health/full")
async def full_health_check():
    """Check application health status."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    scheduler_status = get_scheduler_status()
    
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "database": db_status,
            "redis": "enabled" if REDIS_ENABLED else "disabled",
            "scheduler": {
                "enabled": SCHEDULER_ENABLED,
                "running": scheduler_status.get("running", False),
                "jobs_count": len(scheduler_status.get("jobs", [])),
                "error": scheduler_status.get("error"),
            }
        }
    })

@app.get("/health")
async def health_check():
    return {
        "status": "healthy"
    }

# --- Database Migration Endpoint ---
@app.post("/migrate", tags=["Admin"])
async def migrate_database():
    """Run database migrations (creates tables if they don't exist)."""
    try:
        init_db()
        return {
            "status": "success",
            "message": "Database migration completed successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Migration failed: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


# --- Reset Database Endpoint ---
@app.post("/reset-db", tags=["Admin"])
async def reset_database():
    """
    WARNING: This endpoint drops ALL tables and recreates them.
    All data will be permanently deleted.
    """
    from backend.email.db import Base
    try:
        # Drop all tables
        Base.metadata.drop_all(bind=engine)
        
        # Recreate all tables
        Base.metadata.create_all(bind=engine)
        
        return {
            "status": "success",
            "message": "All tables dropped and recreated successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Database reset failed: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

# --- Routers ---
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(meetings_router, tags=["Meetings"])
app.include_router(stt_router.router, tags=["Speech-to-Text"])
app.include_router(notes_router, tags=["Notes"])

# # --- WebSocket for WebRTC signaling ---
# @app.websocket("/ws/{room_id}")
# async def websocket_endpoint(websocket: WebSocket, room_id: str):
#     await manager.connect(websocket, room_id)
#     try:
#         while True:
#             data = await websocket.receive_text()
#             await manager.broadcast(data, room_id, websocket)
#     except WebSocketDisconnect:
#         manager.disconnect(websocket, room_id)


