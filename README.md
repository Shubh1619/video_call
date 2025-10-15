# Simple Video Call App

A minimal WebRTC-based video calling application with a FastAPI signaling server.

## 🚀 Setup

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend
Open `frontend/index.html` in two browser tabs.

## ⚙️ How It Works
- FastAPI WebSocket acts as the signaling server.
- WebRTC handles peer-to-peer media connection.
- Open same page on two clients to test video call.
