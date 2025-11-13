from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from backend.auth.router import router as auth_router
from backend.meetings.router import router as meetings_router
from backend.scheduler.reminder import start_scheduler
from backend.email.db import init_db
from backend.scheduler.cleanup import scheduler, delete_expired_meetings

# ✅ Import our new STT router and service
from backend.routers import stt as stt_router
from backend.services.stt_service import SttService

app = FastAPI(title="AI for IA - Secure Meeting")

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database ---
@app.on_event("startup")
def on_startup():
    init_db()
    app.state.stt_service = SttService()

    # Start meeting reminder scheduler
    start_scheduler(app)

    # Start auto-clean job every 5 min
    scheduler.add_job(delete_expired_meetings, "interval", minutes=5)
    print("🧹 Auto-clean meeting job started...")



# --- Routers ---
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(meetings_router, tags=["Meetings"])
app.include_router(stt_router.router, tags=["Speech-to-Text"])  # ✅ add STT WebSocket route

