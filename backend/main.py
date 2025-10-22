from fastapi import FastAPI
from backend.auth.router import router as auth_router
from backend.meetings.router import router as meetings_router
from backend.scheduler.reminder import start_scheduler
from backend.core.db import init_db

app = FastAPI()

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(meetings_router, prefix="/meetings", tags=["Meetings"])

start_scheduler(app)