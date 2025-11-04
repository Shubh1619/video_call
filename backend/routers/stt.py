# routers/stt.py
import os
import json
import asyncio
from jose import jwt, JWTError
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from fastapi import HTTPException
from fastapi.websockets import WebSocketState
from fastapi import Request

router = APIRouter()
JWT_SECRET = os.environ.get("JWT_SECRET", "replace_this_secret")  # set in prod


def validate_jwt(token: str, expected_user_id: str, room_id: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {str(e)}")
    # Minimal checks: 'sub' must equal expected_user_id. Add room membership checks if present.
    if payload.get("sub") != expected_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token subject doesn't match user_id")
    # optional: if token contains 'rooms' list, ensure room_id is allowed
    rooms = payload.get("rooms")
    if rooms and room_id not in rooms:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this room")
    return payload


@router.websocket("/ws/stt")
async def stt_ws_endpoint(websocket: WebSocket, token: Optional[str] = Query(None), room_id: Optional[str] = Query(None),
                          user_id: Optional[str] = Query(None)):
    """
    Connect to STT WebSocket.
    Query params:
      - token: JWT
      - room_id: meeting id
      - user_id: id of the speaking user
    After connection, the client must send raw Int16Array binary frames.
    Server broadcasts JSON messages of captions to all connections in same room.

    Example websocket URL:
      ws://host/ws/stt?token=...&room_id=room123&user_id=user123
    """
    if token is None or room_id is None or user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Validate token and basic claims
    try:
        validate_jwt(token, expected_user_id=user_id, room_id=room_id)
    except HTTPException as e:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # get STT service singleton
    stt_service = websocket.app.state.stt_service

    # register connection (so service can broadcast to room)
    await stt_service.register_connection(room_id, user_id, websocket)

    try:
        while True:
            message = await websocket.receive()
            # message can be {'type':'websocket.receive', 'text':..., 'bytes':...}
            if "bytes" in message and message["bytes"] is not None:
                # raw PCM16 binary chunk
                chunk = message["bytes"]
                # push chunk into stt queue
                await stt_service.push_audio_chunk(room_id, user_id, chunk)
            elif "text" in message and message["text"] is not None:
                # allow control JSON messages (e.g., 'end', 'vad', etc.) from client
                try:
                    data = json.loads(message["text"])
                except Exception:
                    continue
                # if client signals stop, close session
                if data.get("type") == "stop":
                    break
            else:
                # ignore ping/pong or other messages
                await asyncio.sleep(0)
    except WebSocketDisconnect:
        pass
    finally:
        await stt_service.unregister_connection(room_id, user_id, websocket)
        try:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close()
        except Exception:
            pass
