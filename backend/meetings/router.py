import asyncio, os, uuid, json, logging
import datetime as dt                     # module as dt
from datetime import datetime, timedelta   # datetime & timedelta class

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

# --- Frontend Directory Path ---
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend'))
if not os.path.isdir(frontend_dir):
    raise RuntimeError(f"Frontend directory not found at path: {frontend_dir}")


# ---------------------------------------------------------
#                 SCHEDULE MEETING
# ---------------------------------------------------------
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
    start_dt = datetime.fromisoformat(start_time)  # FIXED
    end_dt = datetime.fromisoformat(end_time)
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
        owner_id=current_user.id,
        meeting_type="regular"
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    # Send invitations + Reminder
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


# ---------------------------------------------------------
#                 INSTANT MEETING
# ---------------------------------------------------------
@router.post("/instant")
def create_instant_meeting(
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    participants: list[str] = Body([]),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    now = datetime.utcnow()         # FIXED
    end_dt = now + timedelta(hours=1)  # FIXED timedelta
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
        owner_id=current_user.id,
        meeting_type="instant"
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    # Send invitations
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

@router.websocket("/ws/{room_name}")
async def websocket_endpoint(websocket: WebSocket, room_name: str):
    client_host = websocket.client.host if websocket.client else "unknown"
    logging.info(f"🟢 WebSocket connected from {client_host} for room: {room_name}")
    await websocket.accept()
    client_id = ""

    async def keep_alive():
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

            # Join event
            if msg.get("type") == "join":
                client_id = sender_id
                rooms.setdefault(room_name, {})
                rooms[room_name][client_id] = websocket
                logging.info(f"👤 {client_id} joined room {room_name}")

                # Notify others
                for other_id, client_ws in rooms[room_name].items():
                    if other_id != client_id:
                        await client_ws.send_text(data)
                continue

            # Direct message
            recipient_id = msg.get("to")
            if recipient_id:
                if recipient_id in rooms.get(room_name, {}):
                    await rooms[room_name][recipient_id].send_text(data)
            else:
                # Broadcast
                for other_id, client_ws in rooms.get(room_name, {}).items():
                    if other_id != sender_id:
                        await client_ws.send_text(data)

    except WebSocketDisconnect:
        logging.info(f"🔴 {client_id} disconnected from room {room_name}")
        if client_id in rooms.get(room_name, {}):
            del rooms[room_name][client_id]

            for other_id, client_ws in rooms.get(room_name, {}).items():
                await client_ws.send_text(json.dumps({
                    "type": "user-left",
                    "id": client_id
                }))

        if room_name in rooms and not rooms[room_name]:
            del rooms[room_name]
            logging.info(f"🧹 Room {room_name} deleted")

    except Exception as e:
        logging.error(f"❌ WebSocket error in room {room_name}: {e}")


# ---------------------------------------------------------
#                 GET MEETINGS BY DATE
# ---------------------------------------------------------
@router.get("/meetings")
def get_meetings_by_date(
    date: str,  # format: YYYY-MM-DD
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}

    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    meetings = db.query(Meeting).filter(
        Meeting.owner_id == current_user.id,
        Meeting.scheduled_start >= start_of_day,
        Meeting.scheduled_start <= end_of_day
    ).all()

    return {"date": date, "meetings": meetings}
