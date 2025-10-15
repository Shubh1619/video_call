from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
from typing import Dict
import json
import logging

logging.basicConfig(level=logging.INFO)
app = FastAPI()

frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend')
if not os.path.isdir(frontend_dir):
    raise RuntimeError(f"Frontend directory not found at path: {frontend_dir}")

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def read_root():
    return FileResponse(os.path.join(frontend_dir, 'index.html'))

rooms: Dict[str, Dict[str, WebSocket]] = {}

@app.websocket("/ws/{room_name}")
async def websocket_endpoint(websocket: WebSocket, room_name: str):
    await websocket.accept()
    client_id = ""

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            sender_id = msg.get("from")

            # --- MODIFIED: Handle different message types ---
            if msg.get("type") == "join":
                client_id = sender_id
                if room_name not in rooms:
                    rooms[room_name] = {}
                rooms[room_name][client_id] = websocket
                logging.info(f"Client {client_id} joined room {room_name}")
                # Broadcast join to others
                for other_id, client_ws in rooms[room_name].items():
                    if other_id != client_id:
                        await client_ws.send_text(data)
                continue

            recipient_id = msg.get("to")
            if recipient_id:
                # Targeted message (offer, answer, candidate)
                recipient_ws = rooms.get(room_name, {}).get(recipient_id)
                if recipient_ws:
                    await recipient_ws.send_text(data)
            else:
                # Broadcast message (like mute status) to all others in the room
                for other_id, client_ws in rooms.get(room_name, {}).items():
                    if other_id != sender_id:
                        await client_ws.send_text(data)

    except WebSocketDisconnect:
        logging.info(f"Client {client_id} disconnected from room {room_name}")
        if room_name in rooms and client_id in rooms[room_name]:
            del rooms[room_name][client_id]
            # Notify others that this user has left
            for other_id, client_ws in rooms.get(room_name, {}).items():
                await client_ws.send_text(json.dumps({"type": "user-left", "id": client_id}))
            
            if not rooms[room_name]:
                del rooms[room_name]