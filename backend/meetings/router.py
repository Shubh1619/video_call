import asyncio, os, uuid, json, logging
import datetime as dt                     # module as dt
from datetime import datetime, timedelta, timezone   # datetime & timedelta class

from fastapi import APIRouter, Depends, Body, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Dict 

# --- Local Imports ---
from backend.email.db import get_db
from backend.auth.utils import get_current_user
from backend.models.meeting import Meeting
from backend.scheduler.unified_scheduler import schedule_meeting_reminder
from backend.email.utils import send_invitation_emails, send_instant_invitation_emails ,meeting_to_dict
from backend.core.config import MY_DOMAIN
from backend.models.user import User
# ---------------------------------------------------------
#                 ROUTER SETUP
# ---------------------------------------------------------
logging.basicConfig(level=logging.INFO)
router = APIRouter()


# ---------------------------------------------------------
#                 SCHEDULE MEETING
# ---------------------------------------------------------
def parse_datetime_to_utc(dt_str: str) -> datetime:
    """Parse datetime string (naive/local) and convert to UTC."""
    try:
        # Parse the datetime string
        dt = datetime.fromisoformat(dt_str)
    except ValueError:
        # Fallback for other formats
        dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
    
    if dt.tzinfo is None:
        # Treat as local timezone and convert to UTC
        local_tz = datetime.now().astimezone().tzinfo
        dt = dt.replace(tzinfo=local_tz).astimezone(timezone.utc)
    
    return dt

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
    logging.info(f"📅 Received start_time: {start_time}, end_time: {end_time}")
    logging.info(f"📅 System local timezone: {datetime.now().astimezone().tzinfo}")
    
    start_dt = parse_datetime_to_utc(start_time)
    end_dt = parse_datetime_to_utc(end_time)
    
    logging.info(f"📅 Parsed start_dt (UTC): {start_dt}")
    logging.info(f"📅 Parsed start_dt date only: {start_dt.strftime('%Y-%m-%d')}")
        
    room_id = str(uuid.uuid4())[:8]
    join_link = f"{MY_DOMAIN}/meeting/{room_id}"

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
        schedule_meeting_reminder(meeting.id, start_dt, participants)

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
    now = datetime.now(timezone.utc)
    end_dt = now + timedelta(hours=1)
    room_id = str(uuid.uuid4())[:8]
    join_link = f"{MY_DOMAIN}/meeting/{room_id}"

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
                logging.info(f"👤 {client_id} (name: {msg.get('name', 'Unknown')}) joined room {room_name}")

                # Notify others about new user
                for other_id, client_ws in rooms[room_name].items():
                    if other_id != client_id:
                        await client_ws.send_text(json.dumps({
                            "type": "user-joined",
                            "id": client_id,
                            "name": msg.get("name", "User")
                        }))

                # Send list of existing participants to new user
                for other_id in rooms[room_name].keys():
                    if other_id != client_id:
                        await websocket.send_text(json.dumps({
                            "type": "user-joined",
                            "id": other_id,
                            "name": "User"
                        }))
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
    date: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    target_date = datetime.strptime(date, "%Y-%m-%d")
    
    # Use UTC for consistent timezone handling
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    meetings = db.query(Meeting).filter(
        Meeting.owner_id == current_user.id,
        Meeting.scheduled_start >= start_of_day,
        Meeting.scheduled_start <= end_of_day
    ).all()

    return {
        "date": date,
        "meetings": [meeting_to_dict(m) for m in meetings]
    }




@router.get("/user/{user_id}")
def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        return {"error": "User not found"}

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email
    }

@router.get("/meetings/by-month")
def get_meetings_by_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Use UTC for consistent date comparisons
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    meetings = db.query(Meeting).filter(
        Meeting.owner_id == current_user.id,
        Meeting.scheduled_start >= start_date,
        Meeting.scheduled_start < end_date
    ).all()

    # Return dates in YYYY-MM-DD format based on UTC
    return {
        "dates": [m.scheduled_start.strftime("%Y-%m-%d") for m in meetings],
        "meetings": [{"id": m.id, "date": m.scheduled_start.strftime("%Y-%m-%d")} for m in meetings]
    }


# Backward-compatible endpoint (matches frontend expectations)
@router.get("/meetings/month")
def get_meetings_by_month_compat(
    month: str,  # Format: "YYYY-MM"
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        year, mon = map(int, month.split("-"))
    except (ValueError, AttributeError):
        return {"dates": [], "meetings": []}
    
    return get_meetings_by_month(year, mon, db, current_user)


# ---------------------------------------------------------
#                 CLEANUP MEETINGS
# ---------------------------------------------------------
@router.post("/meetings/cleanup")
def cleanup_expired_meetings(
    db: Session = Depends(get_db),
):
    """
    Manually trigger cleanup of expired meetings.
    - Instant meetings older than 2 hours
    - Scheduled meetings 30 minutes after end time
    """
    from backend.scheduler.unified_scheduler import delete_expired_meetings
    
    try:
        delete_expired_meetings()
        return {"message": "Expired meetings cleaned up successfully"}
    except Exception as e:
        logging.error(f"Cleanup failed: {e}")
        return {"error": str(e)}


@router.get("/meetings/expired-count")
def get_expired_meetings_count(
    db: Session = Depends(get_db),
):
    """
    Get count of meetings that would be deleted by cleanup.
    """
    now = datetime.now(timezone.utc)
    
    instant_expired = db.query(Meeting).filter(
        Meeting.meeting_type == "instant",
        Meeting.scheduled_start <= now - timedelta(hours=2)
    ).count()

    scheduled_expired = db.query(Meeting).filter(
        Meeting.meeting_type == "regular",
        Meeting.scheduled_end <= now - timedelta(minutes=30)
    ).count()

    return {
        "instant_expired": instant_expired,
        "scheduled_expired": scheduled_expired,
        "total": instant_expired + scheduled_expired
    }


# ---------------------------------------------------------
#                 DELETE SCHEDULED MEETING
# ---------------------------------------------------------
@router.delete("/meetings/{meeting_id}")
def delete_scheduled_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Delete a scheduled (regular) meeting by ID.
    Only the owner can delete their meeting.
    """
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.owner_id == current_user.id,
        Meeting.meeting_type == "regular"
    ).first()

    if not meeting:
        return JSONResponse(
            status_code=404,
            content={"error": "Scheduled meeting not found or not authorized"}
        )

    db.delete(meeting)
    db.commit()

    logging.info(f"🗑️ Deleted scheduled meeting {meeting_id}")
    return {"message": "Scheduled meeting deleted successfully", "id": meeting_id}


# ---------------------------------------------------------
#                 DEBUG ENDPOINT
# ---------------------------------------------------------
@router.get("/debug/all-meetings")
def debug_get_all_meetings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Debug endpoint to see raw meeting data."""
    meetings = db.query(Meeting).filter(
        Meeting.owner_id == current_user.id
    ).all()
    
    return {
        "meetings": [
            {
                "id": m.id,
                "title": m.title,
                "scheduled_start_raw": str(m.scheduled_start),
                "scheduled_start_date": m.scheduled_start.strftime("%Y-%m-%d") if m.scheduled_start is not None else None,
                "scheduled_start_iso": m.scheduled_start.isoformat() if m.scheduled_start is not None else None,
                "meeting_type": m.meeting_type,
            }
            for m in meetings
        ]
    }

