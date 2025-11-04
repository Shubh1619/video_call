import os
import asyncio
import json
import time
import traceback
from collections import defaultdict
from typing import Dict, Optional, Set, Any

import numpy as np

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

# ✅ Use smaller quantized model to fit Render 512 MB memory limit
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "Systran/faster-whisper-tiny-int8")
SAMPLE_RATE = 16000
BASE_CHUNK_SEC = 0.5   # smaller chunk = lower latency
OVERLAP_SEC = 0.1
MAX_QUEUE_SIZE = 300


class Session:
    def __init__(self, room_id: str, user_id: str):
        self.room_id = room_id
        self.user_id = user_id
        self.queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.active = True


class SttService:
    def __init__(self):
        self.connections: Dict[str, Dict[str, Set[Any]]] = defaultdict(lambda: defaultdict(set))
        self.sessions: Dict[str, Session] = {}
        self.lock = asyncio.Lock()
        self.model = None
        self._model_lock = asyncio.Lock()
        self.loop = asyncio.get_event_loop()

    # ---------------- Model Handling ---------------- #
    async def _ensure_model(self):
        """Lazy load Whisper model only when needed."""
        if self.model:
            return
        if WhisperModel is None:
            print("⚠️ faster-whisper not installed.")
            return

        async with self._model_lock:
            if self.model:
                return

            def load_model():
                print(f"🧠 Loading Whisper model: {MODEL_SIZE}")
                device = "cpu"  # ✅ Force CPU for Render free tier
                compute_type = "int8"  # ✅ Smallest memory footprint
                try:
                    model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute_type)
                    print("✅ Whisper model loaded successfully.")
                    return model
                except MemoryError:
                    print("🚨 Out of memory while loading Whisper model. Using dummy captions.")
                    return None

            self.model = await asyncio.get_event_loop().run_in_executor(None, load_model)

    # ---------------- Connection Management ---------------- #
    async def register_connection(self, room_id: str, user_id: str, websocket):
        async with self.lock:
            self.connections[room_id][user_id].add(websocket)
            key = f"{room_id}::{user_id}"
            if key not in self.sessions:
                sess = Session(room_id, user_id)
                self.sessions[key] = sess
                asyncio.create_task(self._session_worker(sess))

    async def unregister_connection(self, room_id: str, user_id: str, websocket):
        async with self.lock:
            try:
                self.connections[room_id][user_id].discard(websocket)
                if not self.connections[room_id][user_id]:
                    key = f"{room_id}::{user_id}"
                    sess = self.sessions.pop(key, None)
                    if sess:
                        sess.active = False
                        await sess.queue.put(b"")
                    del self.connections[room_id][user_id]
                    if not self.connections[room_id]:
                        del self.connections[room_id]
            except KeyError:
                pass

    async def push_audio_chunk(self, room_id: str, user_id: str, chunk: bytes):
        key = f"{room_id}::{user_id}"
        sess = self.sessions.get(key)
        if not sess:
            sess = Session(room_id, user_id)
            self.sessions[key] = sess
            asyncio.create_task(self._session_worker(sess))
        try:
            await sess.queue.put(chunk)
        except asyncio.QueueFull:
            print(f"⚠️ STT queue full for {room_id}:{user_id}")

    # ---------------- Real-Time Streaming Worker ---------------- #
    async def _session_worker(self, session: Session):
        key = f"{session.room_id}::{session.user_id}"
        sr = SAMPLE_RATE
        bytes_per_sample = 2
        chunk_bytes = int(BASE_CHUNK_SEC * sr * bytes_per_sample)
        overlap_bytes = int(OVERLAP_SEC * sr * bytes_per_sample)
        MAX_BUFFER_SEC = 3
        MAX_BUFFER_BYTES = int(MAX_BUFFER_SEC * sr * bytes_per_sample)

        buf = bytearray()
        t_last = time.time()

        while session.active:
            try:
                data = await asyncio.wait_for(session.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if not data:
                if not session.active:
                    break
                continue

            buf.extend(data)

            # Prevent runaway memory usage
            if len(buf) > MAX_BUFFER_BYTES:
                buf = buf[-MAX_BUFFER_BYTES:]

            now = time.time()
            if len(buf) >= chunk_bytes or (now - t_last) > BASE_CHUNK_SEC * 1.5:
                audio_bytes = bytes(buf)
                buf = bytearray(audio_bytes[-overlap_bytes:])  # keep overlap
                t_last = now
                asyncio.create_task(self._transcribe_and_broadcast(session, audio_bytes, partial=True))

        # Send empty final caption when session ends
        await self.broadcast_to_room(session.room_id, {
            "type": "caption_final",
            "room_id": session.room_id,
            "speaker": session.user_id,
            "text": "",
            "timestamp": time.time(),
            "final": True
        })
        self.sessions.pop(key, None)

    # ---------------- Transcription ---------------- #
    async def _transcribe_and_broadcast(self, session: Session, audio_bytes: bytes, partial: bool):
        await self._ensure_model()
        if not self.model:
            return

        try:
            pcm = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        except Exception as e:
            print("PCM conversion failed:", e)
            return

        try:
            def do_transcribe():
                segments, _ = self.model.transcribe(
                    pcm,
                    beam_size=1,
                    language="en",
                    vad_filter=True
                )
                return " ".join([s.text.strip() for s in segments if s.text.strip()])

            text = await asyncio.get_event_loop().run_in_executor(None, do_transcribe)
            if not text:
                return

            payload = {
                "type": "caption",
                "room_id": session.room_id,
                "speaker": session.user_id,
                "text": text,
                "timestamp": time.time(),
                "final": not partial
            }
            await self.broadcast_to_room(session.room_id, payload)
        except Exception as e:
            print("Transcription error:", e)
            traceback.print_exc()

    # ---------------- Broadcasting ---------------- #
    async def broadcast_to_room(self, room_id: str, message: dict):
        conns = self.connections.get(room_id, {})
        msg = json.dumps(message)
        for user_ws_set in conns.values():
            for ws in list(user_ws_set):
                try:
                    await ws.send_text(msg)
                except Exception:
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    user_ws_set.discard(ws)

    async def shutdown(self):
        for s in list(self.sessions.values()):
            s.active = False
            await s.queue.put(b"")
        await asyncio.sleep(0.5)
