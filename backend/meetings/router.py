from fastapi import APIRouter, Depends, Body, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os, uuid, datetime, json, logging
from typing import Dict

# --- Local Imports ---
from backend.core.db import get_db
from backend.auth.utils import get_current_user
from backend.models.meeting import Meeting
from backend.scheduler.reminder import schedule_reminder
from backend.email.utils import send_invitation_emails, send_instant_invitation_emails
from backend.core.config import MY_DOMAIN

# ---------------------------------------------------------
#                 ROUTER SETUP
# ---------------------------------------------------------
logging.basicConfig(level=logging.INFO)
router = APIRouter()

# --- Define frontend_dir once ---
# This path points to '.../backend/../frontend', which is correct
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend'))
if not os.path.isdir(frontend_dir):
    raise RuntimeError(f"Frontend directory not found at path: {frontend_dir}")


@router.get("/meeting")
def get_meeting(room: str):
    """Serve the meeting HTML page."""
    return FileResponse(os.path.join(frontend_dir, "index.html"))


# ------------------- Schedule Meeting -------------------
@router.post("/schedule")
def schedule_meeting(
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    start_time: str = Body(...),
    end_time: str = Body(...),
    participants: list[str] = Body([]),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    start_dt = datetime.datetime.fromisoformat(start_time)
    end_dt = datetime.datetime.fromisoformat(end_time)
    room_id = str(uuid.uuid4())[:8]
    join_link = f"{MY_DOMAIN}/meeting?room={room_id}"

    meeting = Meeting(
        title=title,
        agenda=agenda,
        scheduled_start=start_dt,
        scheduled_end=end_dt,
        attendee_emails=participants,
        meeting_link=join_link,
        room_id=room_id,
        owner_id=current_user.id
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    # Send invitations + Schedule reminder
    if participants:
        background_tasks.add_task(
            send_invitation_emails,
            recipients=participants,
            organizer_email=current_user.email,
            join_link=join_link,
            title=title,
            agenda=agenda,
            start_dt=start_dt
        )
        schedule_reminder(meeting.id, start_dt, participants)

    return {
        "msg": "Scheduled meeting created.",
        "meeting_id": meeting.id,
        "join_link": join_link,
        "participants": participants
    }


# ------------------- Instant Meeting -------------------
@router.post("/instant")
def create_instant_meeting(
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    participants: list[str] = Body([]),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    now = datetime.datetime.utcnow()
    end_dt = now + datetime.timedelta(hours=1)
    room_id = str(uuid.uuid4())[:8]
    join_link = f"{MY_DOMAIN}/meeting?room={room_id}"

    meeting = Meeting(
        title=title,
        agenda=agenda,
        scheduled_start=now,
        scheduled_end=end_dt,
        attendee_emails=participants,
        meeting_link=join_link,
        room_id=room_id,
        owner_id=current_user.id
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    if participants:
        background_tasks.add_task(
            send_instant_invitation_emails,
            recipients=participants,
            organizer_email=current_user.email,
            join_link=join_link,
            title=title,
            agenda=agenda,
        )

    return {
        "msg": "Instant meeting started.",
        "meeting_id": meeting.id,
        "join_link": join_link,
        "participants": participants
    }

# ---------------------------------------------------------
#                 WEBSOCKET SIGNALING
# ---------------------------------------------------------
rooms: Dict[str, Dict[str, WebSocket]] = {}

# --- ✅ FIXED: Changed from @app.websocket to @router.websocket ---
# Now this route will be correctly included in your main app
@router.websocket("/ws/{room_name}")
async def websocket_endpoint(websocket: WebSocket, room_name: str):
    
    # --- ✅ FIXED: Just call accept(). ---
    # The CORSMiddleware in main.py will handle the origin check.
    await websocket.accept()
    client_id = ""
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            sender_id = msg.get("from")

            # --- Handle Join Event ---
            if msg.get("type") == "join":
                client_id = sender_id
                if room_name not in rooms:
                    rooms[room_name] = {}
                rooms[room_name][client_id] = websocket
                logging.info(f"Client {client_id} joined room {room_name}")

                # Notify others
                for other_id, client_ws in rooms[room_name].items():
                    if other_id != client_id:
                        await client_ws.send_text(data)
                continue

            # --- Handle Direct Messages ---
            recipient_id = msg.get("to")
            if recipient_id:
                recipient_ws = rooms.get(room_name, {}).get(recipient_id)
                if recipient_ws:
                    await recipient_ws.send_text(data)
            else:
                # Broadcast (e.g., mute/unmute)
                for other_id, client_ws in rooms.get(room_name, {}).items():
                    if other_id != sender_id:
                        await client_ws.send_text(data)

    except WebSocketDisconnect:
        logging.info(f"Client {client_id} disconnected from room {room_name}")
        if room_name in rooms and client_id in rooms[room_name]:
            del rooms[room_name][client_id]

            # Notify others
            for other_id, client_ws in rooms.get(room_name, {}).items():
                await client_ws.send_text(json.dumps({
                    "type": "user-left",
                    "id": client_id
                }))

            if not rooms[room_name]:
                del rooms[room_name]