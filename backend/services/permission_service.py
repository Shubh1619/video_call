from __future__ import annotations

from backend.models.meeting import Meeting
from backend.models.participant import Participant

HOST_ONLY_ACTIONS = {
    "start_meeting",
    "end_meeting",
    "admit_user",
    "deny_user",
    "kick_user",
    "mute_user",
    "disable_camera",
    "control_screen_share",
    "start_recording",
    "stop_recording",
    "update_permissions",
}


def check_permission(role: str, action: str, meeting: Meeting) -> tuple[bool, str]:
    role = (role or "guest").lower()
    action = (action or "").lower()

    if action in HOST_ONLY_ACTIONS:
        if role == "host":
            return True, ""
        return False, "Host only action"

    if action in {"chat_group", "join_meeting", "leave_meeting", "mic_self", "camera_self", "view_ai_summary"}:
        return True, ""

    if action == "chat_private":
        if role in {"host", "user"}:
            return True, ""
        return False, "Permission denied"

    if action == "generate_ai_summary":
        if role == "host":
            return True, ""
        if role == "user":
            return (bool(meeting.allow_user_ai), "Feature disabled by host" if not meeting.allow_user_ai else "")
        return False, "Permission denied"

    if action == "toggle_captions":
        if role == "host":
            return True, ""
        if role == "user":
            return (
                bool(meeting.allow_user_captions),
                "Feature disabled by host" if not meeting.allow_user_captions else "",
            )
        return False, "Permission denied"

    if action == "screen_share":
        if role == "host":
            return True, ""
        if role == "user":
            return (
                bool(meeting.allow_user_screen_share),
                "Feature disabled by host" if not meeting.allow_user_screen_share else "",
            )
        if role == "guest":
            return (
                bool(meeting.allow_guest_screen_share),
                "Feature disabled by host" if not meeting.allow_guest_screen_share else "",
            )
        return False, "Permission denied"

    return False, "Permission denied"


def resolve_role_for_user(meeting: Meeting, participant_row: Participant | None, user_id: int | None) -> str:
    if user_id and meeting.owner_id and user_id == meeting.owner_id:
        return "host"
    if participant_row:
        if participant_row.role == "host":
            return "host"
        if participant_row.role in {"participant", "user"}:
            return "user"
    return "guest"

