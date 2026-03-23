import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from threading import Lock

@dataclass
class GuestSession:
    session_id: str
    room_id: str
    name: str
    created_at: datetime
    expires_at: datetime
    is_approved: bool = False
    is_host: bool = False
    user_id: Optional[int] = None
    client_id: Optional[str] = None

class GuestSessionManager:
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._sessions: Dict[str, GuestSession] = {}
        self._room_sessions: Dict[str, Dict[str, GuestSession]] = {}
        self._session_token_prefix = "guest_"
    
    def _generate_session_id(self) -> str:
        return f"{self._session_token_prefix}{secrets.token_urlsafe(32)}"
    
    def _generate_guest_token(self, session_id: str) -> str:
        raw = f"{session_id}:{secrets.token_urlsafe(16)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    
    def create_guest_session(
        self,
        room_id: str,
        name: str,
        user_id: Optional[int] = None,
        is_host: bool = False,
        duration_hours: int = 24
    ) -> tuple[str, str]:
        session_id = self._generate_session_id()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=duration_hours)
        
        session = GuestSession(
            session_id=session_id,
            room_id=room_id,
            name=name,
            created_at=now,
            expires_at=expires_at,
            is_host=is_host,
            user_id=user_id
        )
        
        guest_token = self._generate_guest_token(session_id)
        
        self._sessions[session_id] = session
        if room_id not in self._room_sessions:
            self._room_sessions[room_id] = {}
        self._room_sessions[room_id][session_id] = session
        
        return session_id, guest_token
    
    def get_session(self, session_id: str) -> Optional[GuestSession]:
        session = self._sessions.get(session_id)
        if session and session.expires_at > datetime.now(timezone.utc):
            return session
        elif session:
            self._cleanup_session(session_id)
        return None
    
    def get_session_by_client_id(self, room_id: str, client_id: str) -> Optional[GuestSession]:
        for session in self._room_sessions.get(room_id, {}).values():
            if session.client_id == client_id:
                return session
        return None
    
    def link_client(self, session_id: str, client_id: str):
        session = self.get_session(session_id)
        if session:
            session.client_id = client_id
    
    def approve_guest(self, room_id: str, client_id: str) -> bool:
        session = self.get_session_by_client_id(room_id, client_id)
        if session:
            session.is_approved = True
            return True
        return False
    
    def deny_guest(self, room_id: str, client_id: str) -> bool:
        session = self.get_session_by_client_id(room_id, client_id)
        if session:
            self._cleanup_session(session.session_id)
            return True
        return False
    
    def remove_guest(self, room_id: str, client_id: str) -> bool:
        session = self.get_session_by_client_id(room_id, client_id)
        if session:
            self._cleanup_session(session.session_id)
            return True
        return False
    
    def get_waiting_guests(self, room_id: str) -> List[GuestSession]:
        return [
            s for s in self._room_sessions.get(room_id, {}).values()
            if not s.is_approved and not s.is_host
        ]
    
    def get_approved_guests(self, room_id: str) -> List[GuestSession]:
        return [
            s for s in self._room_sessions.get(room_id, {}).values()
            if s.is_approved
        ]
    
    def get_all_room_sessions(self, room_id: str) -> List[GuestSession]:
        return list(self._room_sessions.get(room_id, {}).values())
    
    def is_host_of_room(self, session_id: str, room_id: str) -> bool:
        session = self.get_session(session_id)
        return session is not None and session.is_host and session.room_id == room_id
    
    def get_host_session(self, room_id: str) -> Optional[GuestSession]:
        for session in self._room_sessions.get(room_id, {}).values():
            if session.is_host:
                return session
        return None
    
    def _cleanup_session(self, session_id: str):
        if session_id in self._sessions:
            session = self._sessions[session_id]
            room_id = session.room_id
            del self._sessions[session_id]
            
            if room_id in self._room_sessions and session_id in self._room_sessions[room_id]:
                del self._room_sessions[room_id][session_id]
                if not self._room_sessions[room_id]:
                    del self._room_sessions[room_id]
    
    def cleanup_expired(self):
        now = datetime.now(timezone.utc)
        expired = [
            sid for sid, s in self._sessions.items()
            if s.expires_at <= now
        ]
        for sid in expired:
            self._cleanup_session(sid)

guest_session_manager = GuestSessionManager()
