from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from backend.auth.router import router as auth_router
from backend.meetings.router import router as meetings_router
from backend.scheduler.reminder import start_scheduler
from backend.email.db import init_db

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
    app.state.stt_service = SttService()  # ✅ Initialize STT service
    start_scheduler(app)


@app.on_event("shutdown")
async def on_shutdown():
    await app.state.stt_service.shutdown()


# --- Routers ---
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(meetings_router, tags=["Meetings"])
app.include_router(stt_router.router, tags=["Speech-to-Text"])  # ✅ add STT WebSocket route


# --- Frontend ---
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
if not os.path.isdir(frontend_dir):
    raise RuntimeError(f"Frontend directory not found at: {frontend_dir}")

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    path = os.path.join(frontend_dir, "favicon.ico")
    if os.path.exists(path):
        return FileResponse(path)
    return {"status": "ok"}
