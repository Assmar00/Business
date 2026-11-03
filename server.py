from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import sqlite3
import time

# Versuche OpenCV und mss zu laden für echten Screen-Capture
try:
    import cv2
    import numpy as np
    import mss
    SCREEN_CAPTURE_AVAILABLE = True
except ImportError:
    SCREEN_CAPTURE_AVAILABLE = False

app = FastAPI(title="Assmar00 God-Mode Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            desktop_name TEXT,
            custom_name TEXT,
            hwid TEXT UNIQUE,
            ip TEXT,
            game TEXT,
            cpu TEXT,
            status TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_string TEXT UNIQUE,
            note TEXT,
            expiry TEXT,
            status TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT,
            username TEXT,
            category TEXT,
            game TEXT,
            message TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/api/stats")
def get_stats():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sessions")
    active_clients = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE status='Offen'")
    open_tickets = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM keys")
    total_keys = cursor.fetchone()[0]
    conn.close()
    return {"active_clients": active_clients, "open_tickets": open_tickets, "total_keys": total_keys}

@app.get("/api/users")
def get_users():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT desktop_name, custom_name, hwid, game, cpu, ip FROM sessions")
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "desktop": r[0],
            "custom_name": r[1] or r[0],
            "hwid": r[2],
            "game": r[3],
            "cpu": r[4],
            "ip": r[5]
        } for r in rows
    ]

class LoaderLogin(BaseModel):
    key: str
    hwid: str
    desktop_name: str
    cpu: str
    game: str

@app.post("/api/loader/auth")
def loader_auth(data: LoaderLogin):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO sessions (desktop_name, custom_name, hwid, game, cpu, status, ip)
        VALUES (?, ?, ?, ?, ?, 'Online', '127.0.0.1')
    """, (data.desktop_name, data.desktop_name, data.hwid, data.game, data.cpu))
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "message": "Zugriff gewährt!"}

# --- LIVE STREAM GENERATOR (15 FPS mit korrigiertem JPEG-Parameter) ---
def generate_frames():
    sct = mss.mss() if SCREEN_CAPTURE_AVAILABLE else None
    monitor = sct.monitors[1] if sct else None

    while True:
        if SCREEN_CAPTURE_AVAILABLE and sct:
            try:
                img = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                frame = cv2.resize(frame, (1280, 720))
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                frame_bytes = buffer.tobytes()
            except Exception:
                frame_bytes = b""
        else:
            img = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(img, f"ASSMAR00 GHOST MODE STREAM // {time.strftime('%H:%M:%S')}", (50, 350), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2, cv2.LINE_AA)
            ret, buffer = cv2.imencode('.jpg', img)
            frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(1.0 / 15.0)

@app.get("/video_feed")
def video_feed(user: str = "Unknown"):
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)