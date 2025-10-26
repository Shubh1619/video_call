from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse # ✅ Import FileResponse
import os # ✅ Import os

from backend.auth.router import router as auth_router
from backend.meetings.router import router as meetings_router
from backend.scheduler.reminder import start_scheduler
from backend.core.db import init_db
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# This is correct and will now apply to your WebSocket route
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(meetings_router) # ✅ Include meetings router

# --- ✅ ADDED: Define frontend_dir ---
# This path points to '../frontend' from where main.py is run
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
if not os.path.isdir(frontend_dir):
    # This check is important for debugging
    raise RuntimeError(f"Frontend directory not found at path: {frontend_dir}. Make sure it's in the root of your project.")

# --- ✅ ADDED: Mount static files ---
# This handles CSS, JS, or image assets if you have them.
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# --- ✅ ADDED: Root route to serve index.html ---
# This serves your HTML file from the base URL (e.g., http://127.0.0.1:10000/)
@app.get("/")
async def root():
    return FileResponse(os.path.join(frontend_dir, 'index.html'))

# --- ✅ ADDED: Favicon route ---
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join(frontend_dir, 'favicon.ico')
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return {"status": "ok"} # Return empty 200 if no icon

start_scheduler(app)