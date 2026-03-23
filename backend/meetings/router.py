import asyncio, os, uuid, json, logging
import datetime as dt
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Body, BackgroundTasks, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.email.db import get_db
from backend.auth.utils import get_current_user, decode_token as decode_jwt_token
from backend.models.meeting import Meeting, MeetingSettings
from backend.scheduler.unified_scheduler import schedule_meeting_reminder
from backend.email.utils import send_invitation_emails, send_instant_invitation_emails, meeting_to_dict
from backend.core.config import MY_DOMAIN
from backend.models.user import User
from backend.services.guest_session import guest_session_manager

logging.basicConfig(level=logging.INFO)
router = APIRouter()


def parse_datetime_to_utc(dt_str: str) -> datetime:
    try:
        dt_obj = datetime.fromisoformat(dt_str)
    except ValueError:
        dt_obj = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
    
    if dt_obj.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        dt_obj = dt_obj.replace(tzinfo=local_tz).astimezone(timezone.utc)
    
    return dt_obj

def get_meeting_settings(db: Session, meeting: Meeting) -> MeetingSettings:
    settings = db.query(MeetingSettings).filter(MeetingSettings.meeting_id == meeting.id).first()
    if not settings:
        settings = MeetingSettings(
            meeting_id=meeting.id,
            max_participants=100,
            chat_enabled=True,
            screen_share_enabled=True,
            waiting_room_enabled=False,
            allow_guest_join=True
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings

@router.post("/schedule")
def schedule_meeting(
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    start_time: str = Body(...),
    end_time: str = Body(...),
    participants: list[str] = Body([]),
    waiting_room: bool = Body(False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    start_dt = parse_datetime_to_utc(start_time)
    end_dt = parse_datetime_to_utc(end_time)
    
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

    settings = get_meeting_settings(db, meeting)
    settings.waiting_room_enabled = waiting_room
    db.commit()

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
        "room_id": room_id,
        "participants": participants,
        "waiting_room_enabled": waiting_room
    }


@router.post("/instant")
def create_instant_meeting(
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    participants: list[str] = Body([]),
    waiting_room: bool = Body(False),
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

    settings = get_meeting_settings(db, meeting)
    settings.waiting_room_enabled = waiting_room
    db.commit()

    session_id, guest_token = guest_session_manager.create_guest_session(
        room_id=room_id,
        name=current_user.name or current_user.email,
        user_id=current_user.id,
        is_host=True
    )

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
        "room_id": room_id,
        "participants": participants,
        "waiting_room_enabled": waiting_room,
        "host_session_id": session_id,
        "host_guest_token": guest_token
    }


@router.get("/meeting/{room_id}")
def get_meeting_info(
    room_id: str,
    db: Session = Depends(get_db)
):
    meeting = db.query(Meeting).filter(Meeting.room_id == room_id).first()
    if not meeting:
        return JSONResponse(status_code=404, content={"error": "Meeting not found"})
    
    settings = get_meeting_settings(db, meeting)
    
    host_user = db.query(User).filter(User.id == meeting.owner_id).first()
    
    return {
        "id": meeting.id,
        "title": meeting.title,
        "agenda": meeting.agenda,
        "room_id": meeting.room_id,
        "meeting_type": meeting.meeting_type,
        "host": {
            "id": meeting.owner_id,
            "name": host_user.name if host_user else "Host",
            "email": host_user.email if host_user else ""
        },
        "settings": {
            "waiting_room_enabled": settings.waiting_room_enabled,
            "allow_guest_join": settings.allow_guest_join,
            "max_participants": settings.max_participants,
            "chat_enabled": settings.chat_enabled,
            "screen_share_enabled": settings.screen_share_enabled
        }
    }


@router.post("/meeting/{room_id}/settings")
def update_meeting_settings(
    room_id: str,
    waiting_room: Optional[bool] = Body(None),
    allow_guest_join: Optional[bool] = Body(None),
    max_participants: Optional[int] = Body(None),
    chat_enabled: Optional[bool] = Body(None),
    screen_share_enabled: Optional[bool] = Body(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.room_id == room_id,
        Meeting.owner_id == current_user.id
    ).first()
    
    if not meeting:
        return JSONResponse(status_code=404, content={"error": "Meeting not found or not authorized"})
    
    settings = get_meeting_settings(db, meeting)
    
    if waiting_room is not None:
        settings.waiting_room_enabled = waiting_room
    if allow_guest_join is not None:
        settings.allow_guest_join = allow_guest_join
    if max_participants is not None:
        settings.max_participants = max_participants
    if chat_enabled is not None:
        settings.chat_enabled = chat_enabled
    if screen_share_enabled is not None:
        settings.screen_share_enabled = screen_share_enabled
    
    db.commit()
    
    return {"message": "Settings updated", "settings": {
        "waiting_room_enabled": settings.waiting_room_enabled,
        "allow_guest_join": settings.allow_guest_join,
        "max_participants": settings.max_participants,
        "chat_enabled": settings.chat_enabled,
        "screen_share_enabled": settings.screen_share_enabled
    }}


@router.post("/guest/session")
def create_guest_session(
    room_id: str = Body(...),
    name: str = Body(...),
    db: Session = Depends(get_db)
):
    meeting = db.query(Meeting).filter(Meeting.room_id == room_id).first()
    if not meeting:
        return JSONResponse(status_code=404, content={"error": "Meeting not found"})
    
    settings = get_meeting_settings(db, meeting)
    if not settings.allow_guest_join:
        return JSONResponse(status_code=403, content={"error": "Guest join is disabled for this meeting"})
    
    session_id, guest_token = guest_session_manager.create_guest_session(
        room_id=room_id,
        name=name,
        user_id=None,
        is_host=False
    )
    
    return {
        "session_id": session_id,
        "guest_token": guest_token,
        "waiting_room_enabled": settings.waiting_room_enabled
    }


@router.post("/auth/host-session")
def create_host_session(
    room_id: str = Body(...),
    token: str = Body(...),
    db: Session = Depends(get_db)
):
    try:
        payload = decode_jwt_token(token)
        email = payload.get("sub")
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            return JSONResponse(status_code=401, content={"error": "Invalid user"})
        
        meeting = db.query(Meeting).filter(
            Meeting.room_id == room_id,
            Meeting.owner_id == user.id
        ).first()
        
        if not meeting:
            return JSONResponse(status_code=403, content={"error": "Not the host of this meeting"})
        
        session_id, host_token = guest_session_manager.create_guest_session(
            room_id=room_id,
            name=user.name or user.email,
            user_id=user.id,
            is_host=True
        )
        
        settings = get_meeting_settings(db, meeting)
        
        return {
            "session_id": session_id,
            "host_token": host_token,
            "host": True,
            "settings": {
                "waiting_room_enabled": settings.waiting_room_enabled,
                "allow_guest_join": settings.allow_guest_join,
                "max_participants": settings.max_participants
            }
        }
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": "Invalid token"})


rooms: Dict[str, Dict[str, WebSocket]] = {}
room_hosts: Dict[str, str] = {}
waiting_room: Dict[str, List[Dict]] = {}

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    client_host_ip = websocket.client.host if websocket.client else "unknown"
    logging.info(f"WebSocket connected from {client_host_ip} for room: {room_id}")
    
    await websocket.accept()
    client_id = ""
    session_id = ""
    user_name = "Guest"
    is_host = False
    is_in_waiting = False

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
            msg_type = msg.get("type")
            
            if msg_type == "join":
                client_id = msg.get("from")
                session_id = msg.get("session_id", "")
                user_name = msg.get("name", "Guest")
                is_host_user = msg.get("is_host", False)
                
                session = guest_session_manager.get_session(session_id)
                if session:
                    is_host = session.is_host
                    user_name = session.name
                    guest_session_manager.link_client(session_id, client_id)
                elif is_host_user:
                    existing_host = guest_session_manager.get_host_session(room_id)
                    if existing_host:
                        is_host = True
                        session_id = existing_host.session_id
                        guest_session_manager.link_client(session_id, client_id)
                
                waiting_room.setdefault(room_id, [])
                rooms.setdefault(room_id, {})
                
                if is_host:
                    room_hosts[room_id] = client_id
                    
                    for wait_entry in waiting_room[room_id]:
                        await websocket.send_text(json.dumps({
                            "type": "waiting-user",
                            "client_id": wait_entry["client_id"],
                            "name": wait_entry["name"]
                        }))
                else:
                    waiting_entry = {
                        "client_id": client_id,
                        "name": user_name,
                        "session_id": session_id,
                        "ws": websocket
                    }
                    waiting_room[room_id].append(waiting_entry)
                    is_in_waiting = True
                    
                    if room_id in room_hosts:
                        host_ws = rooms[room_id].get(room_hosts[room_id])
                        if host_ws:
                            await host_ws.send_text(json.dumps({
                                "type": "waiting-user",
                                "client_id": client_id,
                                "name": user_name
                            }))
                    
                    await websocket.send_text(json.dumps({
                        "type": "waiting",
                        "message": "You are in the waiting room. Please wait for the host to approve."
                    }))
                    continue

            elif msg_type == "approve":
                if client_id == room_hosts.get(room_id):
                    target_client_id = msg.get("target_client_id")
                    waiting_room[room_id] = [
                        w for w in waiting_room.get(room_id, [])
                        if w["client_id"] != target_client_id
                    ]
                    
                    for wait_entry in waiting_room.get(room_id, []):
                        if wait_entry["client_id"] == target_client_id:
                            try:
                                await wait_entry["ws"].send_text(json.dumps({
                                    "type": "approved",
                                    "from": client_id,
                                    "message": "You have been approved to join the meeting."
                                }))
                            except Exception:
                                pass
                            
                            rooms[room_id][target_client_id] = wait_entry["ws"]
                            await wait_entry["ws"].send_text(json.dumps({
                                "type": "user-joined",
                                "id": target_client_id,
                                "name": wait_entry["name"]
                            }))
                            break
                    
                    for other_id, other_ws in rooms[room_id].items():
                        if other_id != target_client_id:
                            try:
                                await other_ws.send_text(json.dumps({
                                    "type": "user-joined",
                                    "id": target_client_id,
                                    "name": msg.get("target_name", "Guest")
                                }))
                            except Exception:
                                pass
                
                continue

            elif msg_type == "deny":
                if client_id == room_hosts.get(room_id):
                    target_client_id = msg.get("target_client_id")
                    waiting_room[room_id] = [
                        w for w in waiting_room.get(room_id, [])
                        if w["client_id"] != target_client_id
                    ]
                    
                    for wait_entry in waiting_room.get(room_id, []):
                        if wait_entry["client_id"] == target_client_id:
                            try:
                                await wait_entry["ws"].send_text(json.dumps({
                                    "type": "denied",
                                    "message": "You have been denied entry to the meeting."
                                }))
                                await wait_entry["ws"].close()
                            except Exception:
                                pass
                            break
                
                continue

            elif msg_type == "remove":
                if client_id == room_hosts.get(room_id):
                    target_client_id = msg.get("target_client_id")
                    
                    if target_client_id in rooms[room_id]:
                        target_ws = rooms[room_id][target_client_id]
                        try:
                            await target_ws.send_text(json.dumps({
                                "type": "removed",
                                "message": "You have been removed from the meeting."
                            }))
                            await target_ws.close()
                        except Exception:
                            pass
                        del rooms[room_id][target_client_id]
                    
                    for other_id, other_ws in rooms[room_id].items():
                        try:
                            await other_ws.send_text(json.dumps({
                                "type": "user-left",
                                "id": target_client_id
                            }))
                        except Exception:
                            pass
                
                continue

            if is_in_waiting:
                await websocket.send_text(json.dumps({
                    "type": "waiting",
                    "message": "You are in the waiting room. Please wait for approval."
                }))
                continue

            if msg_type in ["offer", "answer", "candidate"]:
                recipient_id = msg.get("to")
                if recipient_id and recipient_id in rooms.get(room_id, {}):
                    await rooms[room_id][recipient_id].send_text(data)
                continue

            elif msg_type == "chat-message":
                for other_id, other_ws in rooms.get(room_id, {}).items():
                    if other_id != client_id:
                        try:
                            await other_ws.send_text(data)
                        except Exception:
                            pass
                continue

            elif msg_type == "audio-toggle":
                rooms[room_id][client_id] = websocket
                for other_id, other_ws in rooms[room_id].items():
                    if other_id != client_id:
                        try:
                            await other_ws.send_text(data)
                        except Exception:
                            pass
                continue

            elif msg_type == "video-toggle":
                rooms[room_id][client_id] = websocket
                for other_id, other_ws in rooms[room_id].items():
                    if other_id != client_id:
                        try:
                            await other_ws.send_text(data)
                        except Exception:
                            pass
                continue

            if not is_in_waiting and client_id:
                rooms[room_id][client_id] = websocket
                
                if msg_type == "join":
                    for other_id in rooms[room_id].keys():
                        if other_id != client_id:
                            try:
                                await websocket.send_text(json.dumps({
                                    "type": "user-joined",
                                    "id": other_id,
                                    "name": "Participant"
                                }))
                                await rooms[room_id][other_id].send_text(json.dumps({
                                    "type": "user-joined",
                                    "id": client_id,
                                    "name": user_name,
                                    "is_host": is_host
                                }))
                            except Exception:
                                pass

    except WebSocketDisconnect:
        logging.info(f"User {client_id} disconnected from room {room_id}")
        
        if is_in_waiting:
            waiting_room[room_id] = [
                w for w in waiting_room.get(room_id, [])
                if w["client_id"] != client_id
            ]
            if room_id in room_hosts:
                host_ws = rooms[room_id].get(room_hosts[room_id])
                if host_ws:
                    await host_ws.send_text(json.dumps({
                        "type": "waiting-user-left",
                        "client_id": client_id
                    }))
        else:
            if client_id in rooms.get(room_id, {}):
                del rooms[room_id][client_id]
                
                for other_id, other_ws in rooms.get(room_id, {}).items():
                    try:
                        await other_ws.send_text(json.dumps({
                            "type": "user-left",
                            "id": client_id
                        }))
                    except Exception:
                        pass
                
                if room_hosts.get(room_id) == client_id:
                    del room_hosts[room_id]
                    for wait_entry in waiting_room.get(room_id, []):
                        try:
                            await wait_entry["ws"].send_text(json.dumps({
                                "type": "host-left",
                                "message": "The host has left the meeting. All participants will be disconnected."
                            }))
                            await wait_entry["ws"].close()
                        except Exception:
                            pass
                    waiting_room[room_id] = []
                    
                    for remaining_id, remaining_ws in list(rooms.get(room_id, {}).items()):
                        try:
                            await remaining_ws.send_text(json.dumps({
                                "type": "host-left",
                                "message": "The host has left the meeting."
                            }))
                            await remaining_ws.close()
                        except Exception:
                            pass
                    rooms[room_id] = {}

                if room_id in rooms and not rooms[room_id] and not waiting_room.get(room_id):
                    del rooms[room_id]
                    logging.info(f"Room {room_id} deleted")

    except Exception as e:
        logging.error(f"WebSocket error in room {room_id}: {e}")


@router.get("/meetings")
def get_meetings_by_date(
    date: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    target_date = datetime.strptime(date, "%Y-%m-%d")
    
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

    return {
        "dates": [m.scheduled_start.strftime("%Y-%m-%d") for m in meetings],
        "meetings": [{"id": m.id, "date": m.scheduled_start.strftime("%Y-%m-%d")} for m in meetings]
    }


@router.get("/meetings/month")
def get_meetings_by_month_compat(
    month: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        year, mon = map(int, month.split("-"))
    except (ValueError, AttributeError):
        return {"dates": [], "meetings": []}
    
    return get_meetings_by_month(year, mon, db, current_user)


@router.post("/meetings/cleanup")
def cleanup_expired_meetings(
    db: Session = Depends(get_db),
):
    from backend.scheduler.unified_scheduler import delete_expired_meetings
    
    try:
        delete_expired_meetings()
        return {"message": "Expired meetings cleaned up successfully"}
    except Exception as e:
        logging.error(f"Cleanup failed: {e}")
        return {"error": str(e)}


@router.delete("/meetings/{meeting_id}")
def delete_scheduled_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
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

    logging.info(f"Deleted scheduled meeting {meeting_id}")
    return {"message": "Scheduled meeting deleted successfully", "id": meeting_id}


@router.get("/debug/all-meetings")
def debug_get_all_meetings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    meetings = db.query(Meeting).filter(
        Meeting.owner_id == current_user.id
    ).all()
    
    return {
        "meetings": [
            {
                "id": m.id,
                "title": m.title,
                "scheduled_start_raw": str(m.scheduled_start),
                "scheduled_start_date": m.scheduled_start.strftime("%Y-%m-%d") if m.scheduled_start else None,
                "scheduled_start_iso": m.scheduled_start.isoformat() if m.scheduled_start else None,
                "meeting_type": m.meeting_type,
            }
            for m in meetings
        ]
    }
