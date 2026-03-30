import logging

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from backend.auth.utils import decode_token as decode_jwt_token, get_current_user
from backend.email.db import get_db
from backend.models.meeting import Meeting
from backend.models.participant import Participant
from backend.models.user import User
from backend.services.guest_session import guest_session_manager
from backend.services.meeting_serializer import serialize_meeting
from backend.services.permission_service import check_permission, resolve_role_for_user
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
            "waiting_room_enabled": bool(meeting.waiting_room),
            "allow_guest_join": bool(meeting.allow_guest),
            "max_participants": 100,
            "chat_enabled": True,
            "screen_share_enabled": True,
            "allow_user_ai": bool(meeting.allow_user_ai),
            "allow_user_captions": bool(meeting.allow_user_captions),
            "allow_guest_screen_share": bool(meeting.allow_guest_screen_share),
            "allow_user_screen_share": bool(meeting.allow_user_screen_share),
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

    if not meeting.allow_guest:
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
        "waiting_room_enabled": bool(meeting.waiting_room),
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

        return {
            "session_id": session_id,
            "host_token": host_token,
            "host": True,
            "settings": {
                "waiting_room_enabled": bool(meeting.waiting_room),
                "allow_guest_join": bool(meeting.allow_guest),
                "max_participants": 100,
                "allow_user_ai": bool(meeting.allow_user_ai),
                "allow_user_captions": bool(meeting.allow_user_captions),
                "allow_guest_screen_share": bool(meeting.allow_guest_screen_share),
                "allow_user_screen_share": bool(meeting.allow_user_screen_share),
            },
        }
    except Exception as exc:
        logging.error("Failed to create host session: %s", exc)
        return JSONResponse(status_code=401, content={"error": "Invalid token"})


@router.post("/meeting/{room_id}/permissions")
def update_meeting_permissions(
    room_id: str,
    allow_user_ai: bool | None = Body(None),
    allow_user_captions: bool | None = Body(None),
    allow_guest_screen_share: bool | None = Body(None),
    allow_user_screen_share: bool | None = Body(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    meeting = db.query(Meeting).filter(Meeting.room_id == room_id).first()
    if not meeting:
        return JSONResponse(status_code=404, content={"error": "Meeting not found"})
    if meeting.owner_id != current_user.id:
        return JSONResponse(status_code=403, content={"error": "Host only action"})

    if allow_user_ai is not None:
        meeting.allow_user_ai = bool(allow_user_ai)
    if allow_user_captions is not None:
        meeting.allow_user_captions = bool(allow_user_captions)
    if allow_guest_screen_share is not None:
        meeting.allow_guest_screen_share = bool(allow_guest_screen_share)
    if allow_user_screen_share is not None:
        meeting.allow_user_screen_share = bool(allow_user_screen_share)

    db.commit()
    db.refresh(meeting)
    return {
        "message": "Permissions updated",
        "permissions": {
            "allow_user_ai": meeting.allow_user_ai,
            "allow_user_captions": meeting.allow_user_captions,
            "allow_guest_screen_share": meeting.allow_guest_screen_share,
            "allow_user_screen_share": meeting.allow_user_screen_share,
        },
    }


@router.post("/meeting/{room_id}/generate-ai-summary")
def generate_ai_summary(
    room_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    meeting = db.query(Meeting).options(joinedload(Meeting.owner)).filter(Meeting.room_id == room_id).first()
    if not meeting:
        return JSONResponse(status_code=404, content={"error": "Meeting not found"})

    participant = (
        db.query(Participant)
        .filter(
            Participant.meeting_id == meeting.id,
            func.lower(Participant.email) == (current_user.email or "").strip().lower(),
        )
        .first()
    )
    role = resolve_role_for_user(meeting, participant, current_user.id)
    allowed, reason = check_permission(role, "generate_ai_summary", meeting)
    if not allowed:
        return JSONResponse(status_code=403, content={"error": reason or "Permission denied"})

    return {"message": "AI summary generation accepted", "room_id": room_id}
