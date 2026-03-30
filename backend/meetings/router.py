import asyncio, os, uuid, json, logging
import datetime as dt
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Body, BackgroundTasks, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from backend.email.db import get_db, SessionLocal
from backend.auth.utils import get_current_user, decode_token as decode_jwt_token
from backend.models.meeting import Meeting, MeetingSettings
from backend.scheduler.unified_scheduler import schedule_meeting_reminder
from backend.email.utils import send_invitation_emails, send_instant_invitation_emails, meeting_to_dict
from backend.core.config import MY_DOMAIN, SECRET_KEY
from backend.models.user import User
from backend.services.guest_session import guest_session_manager

JWT_ALGORITHM = "HS256"

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


# ─────────────────────────────────────────────
#  REST endpoints (unchanged)
# ─────────────────────────────────────────────

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

    # Always schedule reminder for owner + attendee_emails from DB.
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
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    host_name: str = Body(None),
    participants: list[str] = Body([]),
    waiting_room: bool = Body(False),
    db: Session = Depends(get_db),
):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    current_user = None
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
            email = payload.get("sub")
            if email:
                current_user = db.query(User).filter(User.email == email).first()
        except JWTError:
            pass

    now = datetime.now(timezone.utc)
    end_dt = now + timedelta(hours=1)
    room_id = str(uuid.uuid4())[:8]

    # ✅ Always use latest domain
    join_link = f"{MY_DOMAIN}/meeting/{room_id}"

    # ✅ Cleaner host handling
    if current_user:
        owner_id = current_user.id
        organizer_email = current_user.email
        host_display_name = current_user.name or current_user.email
    else:
        owner_id = None
        organizer_email = host_name or "guest@meetify"
        host_display_name = host_name or "Guest Host"

    meeting = Meeting(
        title=title,
        agenda=agenda,
        scheduled_start=now,
        scheduled_end=end_dt,
        attendee_emails=participants,
        meeting_link=join_link,
        room_id=room_id,
        owner_id=owner_id,
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
        name=host_display_name,
        user_id=owner_id,
        is_host=True
    )

    # 🔥 FIX: Always send email if participants exist
    if participants:
        print("📧 Sending instant meeting email to:", participants)

        background_tasks.add_task(
            send_instant_invitation_emails,
            recipients=participants,
            organizer_email=organizer_email,
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
def get_meeting_info(room_id: str, db: Session = Depends(get_db)):
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
    
    return {
        "message": "Settings updated",
        "settings": {
            "waiting_room_enabled": settings.waiting_room_enabled,
            "allow_guest_join": settings.allow_guest_join,
            "max_participants": settings.max_participants,
            "chat_enabled": settings.chat_enabled,
            "screen_share_enabled": settings.screen_share_enabled
        }
    }


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


# ─────────────────────────────────────────────
#  In-memory room state
# ─────────────────────────────────────────────

# rooms[room_id][client_id] = WebSocket
rooms: Dict[str, Dict[str, WebSocket]] = {}

# room_hosts[room_id] = client_id of the host
room_hosts: Dict[str, str] = {}

# waiting_rooms[room_id] = list of {client_id, name, session_id, ws}
waiting_rooms: Dict[str, List[Dict]] = {}

# participant names  participant_names[room_id][client_id] = name
participant_names: Dict[str, Dict[str, str]] = {}


# ─────────────────────────────────────────────
#  Helper: safe send
# ─────────────────────────────────────────────

async def safe_send(ws: WebSocket, payload: dict):
    """Send JSON to a WebSocket, silently ignore if connection is gone."""
    try:
        await ws.send_text(json.dumps(payload))
    except Exception as e:
        logging.warning(f"safe_send failed: {e}")


async def broadcast_to_room(room_id: str, payload: dict, exclude_id: str = ""):
    """Broadcast a message to every connected client in a room."""
    for cid, ws in list(rooms.get(room_id, {}).items()):
        if cid != exclude_id:
            await safe_send(ws, payload)


# ─────────────────────────────────────────────
#  Main WebSocket endpoint
# ─────────────────────────────────────────────

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    client_host_ip = websocket.client.host if websocket.client else "unknown"
    logging.info(f"WebSocket connection attempt from {client_host_ip} for room: {room_id}")

    await websocket.accept()

    # Per-connection state
    client_id: str = ""
    user_name: str = "Guest"
    is_host: bool = False
    is_in_waiting: bool = False

    # ── Keep-alive ping task ──────────────────
    async def keep_alive():
        while True:
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
                await asyncio.sleep(20)
            except Exception:
                break

    ping_task = asyncio.create_task(keep_alive())

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            # ── Normalise message types ───────
            if msg_type == "host-join":
                msg_type = "join"
                msg["is_host"] = True
            elif msg_type == "waiting-room-request":
                msg_type = "join"
                msg["is_host"] = False

            # ══════════════════════════════════
            #  JOIN
            # ══════════════════════════════════
            if msg_type == "join":
                client_id  = msg.get("from", str(uuid.uuid4()))
                user_name  = msg.get("name", "Guest")
                session_id = msg.get("session_id", "")
                token      = msg.get("token", "")
                requested_host = bool(msg.get("is_host", False))

                # Resolve role from session manager only.
                # Clients must present a valid host session to enter directly as host.
                session = guest_session_manager.get_session(session_id) if session_id else None
                if session:
                    is_host   = session.is_host
                    user_name = session.name
                    previous_client_id = session.client_id
                    guest_session_manager.link_client(session_id, client_id)
                else:
                    is_host = False
                    previous_client_id = None
                    # Fallback: verify host directly from JWT and meeting ownership.
                    if requested_host and token:
                        db = SessionLocal()
                        try:
                            payload = decode_jwt_token(token)
                            email = payload.get("sub")
                            if email:
                                meeting = db.query(Meeting).filter(Meeting.room_id == room_id).first()
                                if meeting and meeting.owner_id:
                                    owner = db.query(User).filter(User.id == meeting.owner_id).first()
                                    if owner and owner.email == email:
                                        is_host = True
                                        user_name = owner.name or owner.email or user_name
                        except Exception:
                            is_host = False
                        finally:
                            db.close()

                # Ensure room structures exist
                rooms.setdefault(room_id, {})
                waiting_rooms.setdefault(room_id, [])
                participant_names.setdefault(room_id, {})

                if previous_client_id and previous_client_id != client_id:
                    old_active_ws = rooms[room_id].pop(previous_client_id, None)
                    participant_names[room_id].pop(previous_client_id, None)
                    waiting_rooms[room_id] = [
                        w for w in waiting_rooms.get(room_id, [])
                        if w["client_id"] != previous_client_id and w.get("session_id") != session_id
                    ]

                    if room_hosts.get(room_id) == previous_client_id:
                        room_hosts[room_id] = client_id

                    if old_active_ws:
                        await broadcast_to_room(room_id, {
                            "type": "user-left",
                            "id": previous_client_id
                        })

                # ── HOST joins ────────────────
                if is_host:
                    room_hosts[room_id] = client_id
                    rooms[room_id][client_id] = websocket          # FIX: host was never added to rooms
                    participant_names[room_id][client_id] = user_name

                    logging.info(f"Host '{user_name}' ({client_id}) joined room {room_id}")

                    # Tell host about everyone already in the room
                    for other_id in list(rooms[room_id].keys()):
                        if other_id != client_id:
                            other_name = participant_names[room_id].get(other_id, "Participant")
                            await safe_send(websocket, {
                                "type": "user-joined",
                                "id": other_id,
                                "name": other_name
                            })

                    # Tell host about pending waiting-room entries
                    for entry in waiting_rooms[room_id]:
                        await safe_send(websocket, {
                            "type": "waiting-user",
                            "client_id": entry["client_id"],
                            "name": entry["name"]
                        })

                    # Tell existing participants that host joined
                    await broadcast_to_room(room_id, {
                        "type": "user-joined",
                        "id": client_id,
                        "name": user_name,
                        "is_host": True
                    }, exclude_id=client_id)

                # ── GUEST joins ───────────────
                else:
                    if session and session.is_approved:
                        rooms[room_id][client_id] = websocket
                        participant_names[room_id][client_id] = user_name
                        is_in_waiting = False

                        await safe_send(websocket, {
                            "type": "approved",
                            "message": "Welcome back to the meeting."
                        })

                        await broadcast_to_room(room_id, {
                            "type": "user-joined",
                            "id": client_id,
                            "name": user_name
                        }, exclude_id=client_id)

                        for other_id in list(rooms[room_id].keys()):
                            if other_id != client_id:
                                other_name = participant_names[room_id].get(other_id, "Participant")
                                await safe_send(websocket, {
                                    "type": "user-joined",
                                    "id": other_id,
                                    "name": other_name
                                })

                        logging.info(f"Approved guest '{user_name}' ({client_id}) rejoined room {room_id}")
                        continue

                    waiting_rooms[room_id] = [
                        w for w in waiting_rooms.get(room_id, [])
                        if w["client_id"] != client_id and w.get("session_id") != session_id
                    ]
                    waiting_rooms[room_id].append({
                        "client_id": client_id,
                        "name": user_name,
                        "session_id": session_id,
                        "ws": websocket
                    })
                    is_in_waiting = True

                    logging.info(f"Guest '{user_name}' ({client_id}) entered waiting room for {room_id}")

                    # Notify host if present
                    host_id = room_hosts.get(room_id)
                    if host_id and host_id in rooms.get(room_id, {}):
                        await safe_send(rooms[room_id][host_id], {
                            "type": "waiting-user",
                            "client_id": client_id,
                            "name": user_name
                        })

                    await safe_send(websocket, {
                        "type": "waiting",
                        "message": "You are in the waiting room. Please wait for the host to approve."
                    })

                continue  # Done handling join

            # ══════════════════════════════════
            #  Block waiting-room users from
            #  sending anything else
            # ══════════════════════════════════
            if is_in_waiting and client_id in rooms.get(room_id, {}):
                is_in_waiting = False

            if is_in_waiting:
                await safe_send(websocket, {
                    "type": "waiting",
                    "message": "You are in the waiting room. Please wait for approval."
                })
                continue

            # ══════════════════════════════════
            #  APPROVE (host only)
            # ══════════════════════════════════
            if msg_type == "approve":
                if client_id != room_hosts.get(room_id):
                    continue

                target_id = msg.get("target_client_id")

                # FIX: find the entry BEFORE removing it from waiting list
                target_entry = next(
                    (w for w in waiting_rooms.get(room_id, []) if w["client_id"] == target_id),
                    None
                )

                # Remove from waiting list
                waiting_rooms[room_id] = [
                    w for w in waiting_rooms.get(room_id, [])
                    if w["client_id"] != target_id
                ]

                if target_entry:
                    target_ws   = target_entry["ws"]
                    target_name = target_entry["name"]
                    guest_session_manager.approve_guest(room_id, target_id)

                    # Add to active room
                    rooms[room_id][target_id] = target_ws
                    participant_names[room_id][target_id] = target_name

                    # Tell the approved user they can proceed
                    await safe_send(target_ws, {
                        "type": "approved",
                        "message": "You have been approved to join the meeting."
                    })

                    # Tell everyone (including host) that this user joined
                    await broadcast_to_room(room_id, {
                        "type": "user-joined",
                        "id": target_id,
                        "name": target_name
                    })

                    # Tell the newly-admitted user about everyone else
                    for other_id in list(rooms[room_id].keys()):
                        if other_id != target_id:
                            other_name = participant_names[room_id].get(other_id, "Participant")
                            await safe_send(target_ws, {
                                "type": "user-joined",
                                "id": other_id,
                                "name": other_name
                            })

                    logging.info(f"Host approved '{target_name}' ({target_id}) into room {room_id}")

                continue

            # ══════════════════════════════════
            #  DENY (host only)
            # ══════════════════════════════════
            if msg_type == "deny":
                if client_id != room_hosts.get(room_id):
                    continue

                target_id = msg.get("target_client_id")
                target_entry = next(
                    (w for w in waiting_rooms.get(room_id, []) if w["client_id"] == target_id),
                    None
                )

                waiting_rooms[room_id] = [
                    w for w in waiting_rooms.get(room_id, [])
                    if w["client_id"] != target_id
                ]

                if target_entry:
                    await safe_send(target_entry["ws"], {
                        "type": "denied",
                        "message": "You have been denied entry to the meeting."
                    })
                    try:
                        await target_entry["ws"].close()
                    except Exception:
                        pass

                continue

            # ══════════════════════════════════
            #  REMOVE participant (host only)
            # ══════════════════════════════════
            if msg_type == "remove":
                if client_id != room_hosts.get(room_id):
                    continue

                target_id = msg.get("target_client_id")
                target_ws = rooms.get(room_id, {}).pop(target_id, None)
                participant_names.get(room_id, {}).pop(target_id, None)

                if target_ws:
                    await safe_send(target_ws, {
                        "type": "removed",
                        "message": "You have been removed from the meeting."
                    })
                    try:
                        await target_ws.close()
                    except Exception:
                        pass

                # Notify remaining participants
                await broadcast_to_room(room_id, {
                    "type": "user-left",
                    "id": target_id
                })

                continue

            # ══════════════════════════════════
            #  WebRTC signalling (targeted)
            # ══════════════════════════════════
            if msg_type in ("offer", "answer", "candidate"):
                recipient_id = msg.get("to")
                if recipient_id:
                    recipient_ws = rooms.get(room_id, {}).get(recipient_id)
                    if recipient_ws:
                        msg["from"] = client_id   # 🔥 ADD THIS LINE
                        await safe_send(recipient_ws, {
                                        "type": msg_type,
                                        "from": client_id,      # 🔥 VERY IMPORTANT
                                        "to": recipient_id,
                                        "sdp": msg.get("sdp"),
                                        "candidate": msg.get("candidate")
                                    })
                    else:
                        logging.warning(
                            f"Signal '{msg_type}' from {client_id} "
                            f"to unknown recipient {recipient_id} in room {room_id}"
                        )
                continue

            # ══════════════════════════════════
            #  CHAT message (broadcast)
            # ══════════════════════════════════
            if msg_type == "chat-message":
                await broadcast_to_room(room_id, msg, exclude_id=client_id)
                continue

            # ══════════════════════════════════
            #  AUDIO / VIDEO toggle (broadcast)
            # ══════════════════════════════════
            if msg_type in ("audio-toggle", "video-toggle", "update-state"):
                await broadcast_to_room(room_id, msg, exclude_id=client_id)
                continue

            # ══════════════════════════════════
            #  Unhandled — log and ignore
            # ══════════════════════════════════
            logging.warning(f"Unhandled message type '{msg_type}' from {client_id} in room {room_id}")

    # ── Disconnect ────────────────────────────
    except WebSocketDisconnect:
        logging.info(f"Client '{user_name}' ({client_id}) disconnected from room {room_id}")

    except Exception as e:
        logging.error(f"WebSocket error for {client_id} in room {room_id}: {e}", exc_info=True)

    finally:
        ping_task.cancel()

        if is_in_waiting:
            # Remove from waiting room
            waiting_rooms[room_id] = [
                w for w in waiting_rooms.get(room_id, [])
                if w["client_id"] != client_id
            ]
            # Notify host
            host_id = room_hosts.get(room_id)
            if host_id and host_id in rooms.get(room_id, {}):
                await safe_send(rooms[room_id][host_id], {
                    "type": "waiting-user-left",
                    "client_id": client_id
                })
        else:
            # Remove from active room
            rooms.get(room_id, {}).pop(client_id, None)
            participant_names.get(room_id, {}).pop(client_id, None)

            # Notify remaining participants
            if rooms.get(room_id):
                await broadcast_to_room(room_id, {
                    "type": "user-left",
                    "id": client_id
                })

            # Handle host disconnect
            if room_hosts.get(room_id) == client_id:
                logging.info(f"Host left room {room_id} — closing room")
                del room_hosts[room_id]

                # Notify and close all waiting users
                for entry in waiting_rooms.get(room_id, []):
                    await safe_send(entry["ws"], {
                        "type": "host-left",
                        "message": "The host has left. The meeting is now closed."
                    })
                    try:
                        await entry["ws"].close()
                    except Exception:
                        pass
                waiting_rooms[room_id] = []

                # Notify and close remaining participants
                for _, ws in list(rooms.get(room_id, {}).items()):
                    await safe_send(ws, {
                        "type": "host-left",
                        "message": "The host has left. The meeting is now closed."
                    })
                    try:
                        await ws.close()
                    except Exception:
                        pass
                rooms[room_id] = {}

            # Clean up empty rooms
            if (
                room_id in rooms
                and not rooms[room_id]
                and not waiting_rooms.get(room_id)
            ):
                rooms.pop(room_id, None)
                waiting_rooms.pop(room_id, None)
                participant_names.pop(room_id, None)
                logging.info(f"Room {room_id} cleaned up")


# ─────────────────────────────────────────────
#  Guest WebSocket registration endpoint
# ─────────────────────────────────────────────

@router.websocket("/ws-guest/{room_id}")
async def websocket_guest_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    try:
        raw  = await websocket.receive_text()
        msg  = json.loads(raw)

        if msg.get("type") == "register":
            name            = msg.get("name", "Guest")
            is_host_request = msg.get("is_host", False)

            session_id, guest_token = guest_session_manager.create_guest_session(
                room_id=room_id,
                name=name,
                user_id=None,
                is_host=is_host_request
            )

            await websocket.send_json({
                "type":       "registered",
                "session_id": session_id,
                "guest_token": guest_token,
                "name":       name
            })
    except Exception as e:
        logging.error(f"ws-guest error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ─────────────────────────────────────────────
#  Remaining REST endpoints (unchanged)
# ─────────────────────────────────────────────

@router.get("/meetings")
def get_meetings_by_date(
    date: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    target_date  = datetime.strptime(date, "%Y-%m-%d")
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day   = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    meetings = db.query(Meeting).filter(
        Meeting.owner_id == current_user.id,
        Meeting.scheduled_start >= start_of_day,
        Meeting.scheduled_start <= end_of_day
    ).all()

    return {"date": date, "meetings": [meeting_to_dict(m) for m in meetings]}


@router.get("/user/{user_id}")
def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "User not found"}
    return {"id": user.id, "name": user.name, "email": user.email}


@router.get("/meetings/by-month")
def get_meetings_by_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    end_date   = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12 \
                 else datetime(year, month + 1, 1, tzinfo=timezone.utc)

    meetings = db.query(Meeting).filter(
        Meeting.owner_id == current_user.id,
        Meeting.scheduled_start >= start_date,
        Meeting.scheduled_start < end_date
    ).all()

    return {
        "dates":    [m.scheduled_start.strftime("%Y-%m-%d") for m in meetings],
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
def cleanup_expired_meetings(db: Session = Depends(get_db)):
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
    meetings = db.query(Meeting).filter(Meeting.owner_id == current_user.id).all()
    return {
        "meetings": [
            {
                "id":                    m.id,
                "title":                 m.title,
                "scheduled_start_raw":   str(m.scheduled_start),
                "scheduled_start_date":  m.scheduled_start.strftime("%Y-%m-%d") if m.scheduled_start else None,
                "scheduled_start_iso":   m.scheduled_start.isoformat() if m.scheduled_start else None,
                "meeting_type":          m.meeting_type,
            }
            for m in meetings
        ]
    }
