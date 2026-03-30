import logging

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from backend.auth.utils import decode_token as decode_jwt_token
from backend.email.db import get_db
from backend.meetings.common import get_meeting_settings
from backend.models.meeting import Meeting
from backend.models.user import User
from backend.services.guest_session import guest_session_manager
from backend.services.meeting_serializer import serialize_meeting
from backend.services.time_service import get_utc_now

router = APIRouter()


@router.get("/meeting/{room_id}")
def get_meeting_info(room_id: str, db: Session = Depends(get_db)):
    meeting = (
        db.query(Meeting)
        .options(joinedload(Meeting.owner))
        .filter(Meeting.room_id == room_id)
        .first()
    )
    if not meeting:
        return JSONResponse(status_code=404, content={"error": "Meeting not found"})

    settings = get_meeting_settings(db, meeting)
    host_user = meeting.owner

    return {
        "meeting": serialize_meeting(meeting, now_utc=get_utc_now(), role="owner"),
        "id": meeting.id,
        "title": meeting.title,
        "agenda": meeting.agenda,
        "room_id": meeting.room_id,
        "meeting_type": meeting.meeting_type,
        "host": {
            "id": meeting.owner_id,
            "name": host_user.name if host_user else "Host",
            "email": host_user.email if host_user else "",
        },
        "settings": {
            "waiting_room_enabled": settings.waiting_room_enabled,
            "allow_guest_join": settings.allow_guest_join,
            "max_participants": settings.max_participants,
            "chat_enabled": settings.chat_enabled,
            "screen_share_enabled": settings.screen_share_enabled,
        },
    }


@router.post("/guest/session")
def create_guest_session(
    room_id: str = Body(...),
    name: str = Body(...),
    db: Session = Depends(get_db),
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
        is_host=False,
    )

    return {
        "session_id": session_id,
        "guest_token": guest_token,
        "waiting_room_enabled": settings.waiting_room_enabled,
    }


@router.post("/auth/host-session")
def create_host_session(
    room_id: str = Body(...),
    token: str = Body(...),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_jwt_token(token)
        email = payload.get("sub")
        user = db.query(User).filter(User.email == email).first()

        if not user:
            return JSONResponse(status_code=401, content={"error": "Invalid user"})

        meeting = db.query(Meeting).filter(Meeting.room_id == room_id, Meeting.owner_id == user.id).first()
        if not meeting:
            return JSONResponse(status_code=403, content={"error": "Not the host of this meeting"})

        session_id, host_token = guest_session_manager.create_guest_session(
            room_id=room_id,
            name=user.name or user.email,
            user_id=user.id,
            is_host=True,
        )

        settings = get_meeting_settings(db, meeting)

        return {
            "session_id": session_id,
            "host_token": host_token,
            "host": True,
            "settings": {
                "waiting_room_enabled": settings.waiting_room_enabled,
                "allow_guest_join": settings.allow_guest_join,
                "max_participants": settings.max_participants,
            },
        }
    except Exception as exc:
        logging.error("Failed to create host session: %s", exc)
        return JSONResponse(status_code=401, content={"error": "Invalid token"})
