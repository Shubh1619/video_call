import asyncio ,os, uuid, datetime, json, logging
from fastapi import APIRouter, Depends, Body, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Dict 

# --- Local Imports ---
from backend.email.db import get_db
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

# --- ✅ Fully updated WebSocket endpoint for Render deployment ---
@router.websocket("/ws/{room_name}")
async def websocket_endpoint(websocket: WebSocket, room_name: str):
    client_host = websocket.client.host if websocket.client else "unknown"
    logging.info(f"🟢 Incoming WebSocket connection from {client_host} for room: {room_name}")
    await websocket.accept()
    client_id = ""

    # --- ✅ Keep connection alive to prevent Render timeouts ---
    async def keep_alive():
        """Send heartbeat messages periodically to avoid idle disconnects."""
        while True:
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
                await asyncio.sleep(20)
            except Exception:
                break

    asyncio.create_task(keep_alive())

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            sender_id = msg.get("from")

            # --- ✅ Handle Join Event ---
            if msg.get("type") == "join":
                client_id = sender_id
                if room_name not in rooms:
                    rooms[room_name] = {}
                rooms[room_name][client_id] = websocket
                logging.info(f"👤 Client {client_id} joined room {room_name}")

                # Notify other participants
                for other_id, client_ws in rooms[room_name].items():
                    if other_id != client_id:
                        try:
                            await client_ws.send_text(data)
                        except Exception as e:
                            logging.warning(f"⚠️ Failed to send join to {other_id}: {e}")
                continue

            # --- ✅ Handle Direct Messages ---
            recipient_id = msg.get("to")
            if recipient_id:
                recipient_ws = rooms.get(room_name, {}).get(recipient_id)
                if recipient_ws:
                    try:
                        await recipient_ws.send_text(data)
                    except Exception as e:
                        logging.warning(f"⚠️ Failed to send message to {recipient_id}: {e}")
            else:
                # --- ✅ Broadcast Events (e.g., mute/unmute, offers, etc.) ---
                for other_id, client_ws in rooms.get(room_name, {}).items():
                    if other_id != sender_id:
                        try:
                            await client_ws.send_text(data)
                        except Exception as e:
                            logging.warning(f"⚠️ Broadcast send error to {other_id}: {e}")

    except WebSocketDisconnect:
        logging.info(f"🔴 Client {client_id} disconnected from room {room_name}")
        if room_name in rooms and client_id in rooms[room_name]:
            del rooms[room_name][client_id]

            # Notify others that this user left
            for other_id, client_ws in rooms.get(room_name, {}).items():
                try:
                    await client_ws.send_text(json.dumps({
                        "type": "user-left",
                        "id": client_id
                    }))
                except Exception as e:
                    logging.warning(f"⚠️ Failed to notify {other_id} about {client_id} leaving: {e}")

            # Clean up empty rooms
            if not rooms[room_name]:
                del rooms[room_name]
                logging.info(f"🧹 Room {room_name} deleted (no active participants)")

    except Exception as e:
        logging.error(f"❌ Unexpected error in WebSocket room {room_name}: {e}")
        if client_id and room_name in rooms and client_id in rooms[room_name]:
            del rooms[room_name][client_id]
            if not rooms[room_name]:
                del rooms[room_name]
