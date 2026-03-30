import asyncio
import json
import logging
import uuid
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.auth.utils import decode_token as decode_jwt_token
from backend.email.db import SessionLocal
from backend.models.meeting import Meeting
from backend.models.user import User
from backend.services.guest_session import guest_session_manager

router = APIRouter()

rooms: Dict[str, Dict[str, WebSocket]] = {}
room_hosts: Dict[str, str] = {}
waiting_rooms: Dict[str, List[Dict]] = {}
participant_names: Dict[str, Dict[str, str]] = {}


async def safe_send(ws: WebSocket, payload: dict):
    try:
        await ws.send_text(json.dumps(payload))
    except Exception as exc:
        logging.warning("safe_send failed: %s", exc)


async def broadcast_to_room(room_id: str, payload: dict, exclude_id: str = ""):
    for cid, ws in list(rooms.get(room_id, {}).items()):
        if cid != exclude_id:
            await safe_send(ws, payload)


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    client_host_ip = websocket.client.host if websocket.client else "unknown"
    logging.info("WebSocket connection attempt from %s for room: %s", client_host_ip, room_id)

    await websocket.accept()
    client_id: str = ""
    user_name: str = "Guest"
    is_host: bool = False
    is_in_waiting: bool = False

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

            if msg_type == "host-join":
                msg_type = "join"
                msg["is_host"] = True
            elif msg_type == "waiting-room-request":
                msg_type = "join"
                msg["is_host"] = False

            if msg_type == "join":
                client_id = msg.get("from", str(uuid.uuid4()))
                user_name = msg.get("name", "Guest")
                session_id = msg.get("session_id", "")
                token = msg.get("token", "")
                requested_host = bool(msg.get("is_host", False))

                session = guest_session_manager.get_session(session_id) if session_id else None
                if session:
                    is_host = session.is_host
                    user_name = session.name
                    previous_client_id = session.client_id
                    guest_session_manager.link_client(session_id, client_id)
                else:
                    is_host = False
                    previous_client_id = None
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

                rooms.setdefault(room_id, {})
                waiting_rooms.setdefault(room_id, [])
                participant_names.setdefault(room_id, {})

                if previous_client_id and previous_client_id != client_id:
                    old_active_ws = rooms[room_id].pop(previous_client_id, None)
                    participant_names[room_id].pop(previous_client_id, None)
                    waiting_rooms[room_id] = [
                        w
                        for w in waiting_rooms.get(room_id, [])
                        if w["client_id"] != previous_client_id and w.get("session_id") != session_id
                    ]

                    if room_hosts.get(room_id) == previous_client_id:
                        room_hosts[room_id] = client_id

                    if old_active_ws:
                        await broadcast_to_room(room_id, {"type": "user-left", "id": previous_client_id})

                if is_host:
                    room_hosts[room_id] = client_id
                    rooms[room_id][client_id] = websocket
                    participant_names[room_id][client_id] = user_name

                    for other_id in list(rooms[room_id].keys()):
                        if other_id != client_id:
                            other_name = participant_names[room_id].get(other_id, "Participant")
                            await safe_send(websocket, {"type": "user-joined", "id": other_id, "name": other_name})

                    for entry in waiting_rooms[room_id]:
                        await safe_send(websocket, {
                            "type": "waiting-user",
                            "client_id": entry["client_id"],
                            "name": entry["name"],
                        })

                    await broadcast_to_room(
                        room_id,
                        {"type": "user-joined", "id": client_id, "name": user_name, "is_host": True},
                        exclude_id=client_id,
                    )
                else:
                    if session and session.is_approved:
                        rooms[room_id][client_id] = websocket
                        participant_names[room_id][client_id] = user_name
                        is_in_waiting = False

                        await safe_send(websocket, {"type": "approved", "message": "Welcome back to the meeting."})

                        await broadcast_to_room(
                            room_id,
                            {"type": "user-joined", "id": client_id, "name": user_name},
                            exclude_id=client_id,
                        )

                        for other_id in list(rooms[room_id].keys()):
                            if other_id != client_id:
                                other_name = participant_names[room_id].get(other_id, "Participant")
                                await safe_send(websocket, {"type": "user-joined", "id": other_id, "name": other_name})

                        continue

                    waiting_rooms[room_id] = [
                        w
                        for w in waiting_rooms.get(room_id, [])
                        if w["client_id"] != client_id and w.get("session_id") != session_id
                    ]
                    waiting_rooms[room_id].append(
                        {"client_id": client_id, "name": user_name, "session_id": session_id, "ws": websocket}
                    )
                    is_in_waiting = True

                    host_id = room_hosts.get(room_id)
                    if host_id and host_id in rooms.get(room_id, {}):
                        await safe_send(rooms[room_id][host_id], {
                            "type": "waiting-user",
                            "client_id": client_id,
                            "name": user_name,
                        })

                    await safe_send(websocket, {
                        "type": "waiting",
                        "message": "You are in the waiting room. Please wait for the host to approve.",
                    })

                continue

            if is_in_waiting and client_id in rooms.get(room_id, {}):
                is_in_waiting = False

            if is_in_waiting:
                await safe_send(websocket, {
                    "type": "waiting",
                    "message": "You are in the waiting room. Please wait for approval.",
                })
                continue

            if msg_type == "approve":
                if client_id != room_hosts.get(room_id):
                    continue

                target_id = msg.get("target_client_id")
                target_entry = next((w for w in waiting_rooms.get(room_id, []) if w["client_id"] == target_id), None)
                waiting_rooms[room_id] = [w for w in waiting_rooms.get(room_id, []) if w["client_id"] != target_id]

                if target_entry:
                    target_ws = target_entry["ws"]
                    target_name = target_entry["name"]
                    guest_session_manager.approve_guest(room_id, target_id)

                    rooms[room_id][target_id] = target_ws
                    participant_names[room_id][target_id] = target_name

                    await safe_send(target_ws, {"type": "approved", "message": "You have been approved to join the meeting."})
                    await broadcast_to_room(room_id, {"type": "user-joined", "id": target_id, "name": target_name})

                    for other_id in list(rooms[room_id].keys()):
                        if other_id != target_id:
                            other_name = participant_names[room_id].get(other_id, "Participant")
                            await safe_send(target_ws, {"type": "user-joined", "id": other_id, "name": other_name})

                continue

            if msg_type == "deny":
                if client_id != room_hosts.get(room_id):
                    continue

                target_id = msg.get("target_client_id")
                target_entry = next((w for w in waiting_rooms.get(room_id, []) if w["client_id"] == target_id), None)
                waiting_rooms[room_id] = [w for w in waiting_rooms.get(room_id, []) if w["client_id"] != target_id]

                if target_entry:
                    await safe_send(target_entry["ws"], {
                        "type": "denied",
                        "message": "You have been denied entry to the meeting.",
                    })
                    try:
                        await target_entry["ws"].close()
                    except Exception:
                        pass

                continue

            if msg_type == "remove":
                if client_id != room_hosts.get(room_id):
                    continue

                target_id = msg.get("target_client_id")
                target_ws = rooms.get(room_id, {}).pop(target_id, None)
                participant_names.get(room_id, {}).pop(target_id, None)

                if target_ws:
                    await safe_send(target_ws, {
                        "type": "removed",
                        "message": "You have been removed from the meeting.",
                    })
                    try:
                        await target_ws.close()
                    except Exception:
                        pass

                await broadcast_to_room(room_id, {"type": "user-left", "id": target_id})
                continue

            if msg_type in ("offer", "answer", "candidate"):
                recipient_id = msg.get("to")
                if recipient_id:
                    recipient_ws = rooms.get(room_id, {}).get(recipient_id)
                    if recipient_ws:
                        await safe_send(
                            recipient_ws,
                            {
                                "type": msg_type,
                                "from": client_id,
                                "to": recipient_id,
                                "sdp": msg.get("sdp"),
                                "candidate": msg.get("candidate"),
                            },
                        )
                continue

            if msg_type == "chat-message":
                await broadcast_to_room(room_id, msg, exclude_id=client_id)
                continue

            if msg_type in ("audio-toggle", "video-toggle", "update-state"):
                await broadcast_to_room(room_id, msg, exclude_id=client_id)
                continue

    except WebSocketDisconnect:
        logging.info("Client '%s' (%s) disconnected from room %s", user_name, client_id, room_id)
    except Exception as exc:
        logging.error("WebSocket error for %s in room %s: %s", client_id, room_id, exc, exc_info=True)
    finally:
        ping_task.cancel()

        if is_in_waiting:
            waiting_rooms[room_id] = [w for w in waiting_rooms.get(room_id, []) if w["client_id"] != client_id]
            host_id = room_hosts.get(room_id)
            if host_id and host_id in rooms.get(room_id, {}):
                await safe_send(rooms[room_id][host_id], {"type": "waiting-user-left", "client_id": client_id})
        else:
            rooms.get(room_id, {}).pop(client_id, None)
            participant_names.get(room_id, {}).pop(client_id, None)

            if rooms.get(room_id):
                await broadcast_to_room(room_id, {"type": "user-left", "id": client_id})

            if room_hosts.get(room_id) == client_id:
                del room_hosts[room_id]

                for entry in waiting_rooms.get(room_id, []):
                    await safe_send(entry["ws"], {
                        "type": "host-left",
                        "message": "The host has left. The meeting is now closed.",
                    })
                    try:
                        await entry["ws"].close()
                    except Exception:
                        pass
                waiting_rooms[room_id] = []

                for _, ws in list(rooms.get(room_id, {}).items()):
                    await safe_send(ws, {
                        "type": "host-left",
                        "message": "The host has left. The meeting is now closed.",
                    })
                    try:
                        await ws.close()
                    except Exception:
                        pass
                rooms[room_id] = {}

            if room_id in rooms and not rooms[room_id] and not waiting_rooms.get(room_id):
                rooms.pop(room_id, None)
                waiting_rooms.pop(room_id, None)
                participant_names.pop(room_id, None)


@router.websocket("/ws-guest/{room_id}")
async def websocket_guest_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        msg = json.loads(raw)

        if msg.get("type") == "register":
            name = msg.get("name", "Guest")
            is_host_request = msg.get("is_host", False)

            session_id, guest_token = guest_session_manager.create_guest_session(
                room_id=room_id,
                name=name,
                user_id=None,
                is_host=is_host_request,
            )

            await websocket.send_json(
                {"type": "registered", "session_id": session_id, "guest_token": guest_token, "name": name}
            )
    except Exception as exc:
        logging.error("ws-guest error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
