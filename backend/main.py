from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from datetime import datetime, timezone
import os

from backend.auth.router import router as auth_router
from backend.meetings.router import router as meetings_router
from backend.scheduler.unified_scheduler import start_all_schedulers, shutdown_all_schedulers, get_scheduler_status
from backend.email.db import init_db, engine
from backend.notes.routes import router as notes_router
from backend.routers import stt as stt_router
from backend.services.stt_service import SttService
from backend.core.rate_limit import limiter
from backend.core.config import CORS_ORIGINS, REDIS_ENABLED

app = FastAPI(title="AI Meeting Assistant - Secure Meeting")

# --- Rate Limiting Setup ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS (Temporarily allow all for development) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database ---
@app.on_event("startup")
async def on_startup():
    init_db()
    app.state.stt_service = SttService()
    start_all_schedulers()
    print("✓ Application started successfully")

@app.on_event("shutdown")
async def on_shutdown():
    shutdown_all_schedulers()
    print("✓ Application shutdown complete")

# --- Health Check Endpoint ---
@app.get("/health", tags=["Health"])
async def health_check():
    """Check application health status."""
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
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
                "running": scheduler_status.get("running", False),
                "jobs_count": len(scheduler_status.get("jobs", []))
            }
        }
    })

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
