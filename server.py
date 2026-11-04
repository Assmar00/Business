import os
import sqlite3
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import base64
import time

app = FastAPI(title="Assmar00 On-Demand Control", version="31.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database.db"
active_streams = {}
viewers_watching = set()
pending_messages = {}  # Zwischenspeicher für Remote-Nachrichten an Clients

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            desktop TEXT PRIMARY KEY,
            custom_name TEXT DEFAULT 'Client',
            hwid TEXT,
            ip TEXT,
            cpu TEXT,
            gpu TEXT DEFAULT 'Unknown',
            motherboard TEXT DEFAULT 'Unknown',
            ram TEXT DEFAULT 'Unknown',
            os_build TEXT DEFAULT 'Unknown',
            game TEXT DEFAULT 'Idle',
            license_key TEXT DEFAULT '',
            expiry TEXT DEFAULT 'Lifetime',
            fps INTEGER DEFAULT 0,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key_code TEXT PRIMARY KEY,
            note TEXT,
            expiry TEXT,
            status TEXT DEFAULT 'Aktiv'
        )
    """)
    cursor.execute("INSERT OR REPLACE INTO global_settings (key, value) VALUES ('latest_version', '1.0.1')", ())
    cursor.execute("""
        INSERT OR IGNORE INTO keys (key_code, note, expiry, status)
        VALUES ('ASR-9812-PAUL', 'Master Standard Key', '2026-12-31', 'Aktiv')
    """)
    conn.commit()
    conn.close()

init_db()

class ClientData(BaseModel):
    desktop: str
    custom_name: str = "Client"
    hwid: str = ""
    ip: str = "127.0.0.1"
    cpu: str = "Unknown"
    gpu: str = "Unknown"
    motherboard: str = "Unknown"
    ram: str = "Unknown"
    os_build: str = "Unknown"
    game: str = "Idle"
    license_key: str = ""
    expiry: str = "Lifetime"
    fps: int = 0

class FrameData(BaseModel):
    desktop: str
    frame_b64: str

class KeyData(BaseModel):
    key_code: str
    note: str
    expiry: str

class MessageData(BaseModel):
    desktop: str
    message: str

@app.get("/", response_class=HTMLResponse)
def serve_admin():
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>Fehler: admin.html nicht gefunden!</h3>"

@app.get("/api/users")
def get_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# --- REMOTE MESSAGING API ---
@app.post("/api/admin/send_message")
def send_client_message(data: MessageData):
    pending_messages[data.desktop] = data.message
    return {"status": "success", "message": "Nachricht eingereiht"}
# ----------------------------

# --- AUTO-UPDATER API ---
@app.get("/api/update/check")
def check_update():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM global_settings WHERE key = 'latest_version'")
    row = cursor.fetchone()
    conn.close()
    return {"latest_version": row[0] if row else "1.0.0"}

@app.get("/api/update/download")
def download_update():
    if os.path.exists("firefox.py"):
        return FileResponse("firefox.py", media_type="text/plain", filename="firefox.py")
    raise HTTPException(status_code=404, detail="Nicht gefunden")
# ------------------------

# --- KEY MANAGEMENT API ---
@app.get("/api/keys")
def get_keys():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keys")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/keys/add")
def add_key(data: KeyData):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO keys (key_code, note, expiry, status) VALUES (?, ?, ?, 'Aktiv')", 
                       (data.key_code, data.note, data.expiry))
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))
    conn.close()
    return {"status": "success"}

@app.post("/api/keys/delete")
def delete_key(data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM keys WHERE key_code = ?", (data.get("key_code"),))
    conn.commit()
    conn.close()
    return {"status": "deleted"}
# --------------------------

@app.post("/api/client/heartbeat")
def client_heartbeat(data: ClientData):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO clients (desktop, custom_name, hwid, ip, cpu, gpu, motherboard, ram, os_build, game, license_key, expiry, fps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(desktop) DO UPDATE SET
        custom_name=excluded.custom_name, hwid=excluded.hwid, ip=excluded.ip,
        cpu=excluded.cpu, gpu=excluded.gpu, motherboard=excluded.motherboard,
        ram=excluded.ram, os_build=excluded.os_build, game=excluded.game,
        license_key=excluded.license_key, expiry=excluded.expiry, fps=excluded.fps,
        last_seen=CURRENT_TIMESTAMP
    """, (data.desktop, data.custom_name, data.hwid, data.ip, data.cpu, data.gpu, data.motherboard, data.ram, data.os_build, data.game, data.license_key, data.expiry, data.fps))
    conn.commit()
    conn.close()
    
    # Nachricht für diesen Client abholen (falls vorhanden)
    alert_msg = pending_messages.pop(data.desktop, None)
    is_active = data.desktop in viewers_watching
    return {"status": "success", "stream_active": is_active, "alert_message": alert_msg}

@app.get("/api/stop_stream")
def stop_stream(user: str):
    if user in viewers_watching: viewers_watching.remove(user)
    if user in active_streams: del active_streams[user]
    return {"status": "stopped"}

@app.post("/api/client/frame")
def client_frame(data: FrameData):
    if data.desktop in viewers_watching and data.frame_b64:
        try:
            active_streams[data.desktop] = base64.b64decode(data.frame_b64)
        except:
            pass
    return {"status": "success"}

@app.get("/video_feed")
def video_feed(user: str):
    viewers_watching.add(user)
    def generate_stream():
        try:
            while user in viewers_watching:
                if user in active_streams and active_streams[user]:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + active_streams[user] + b'\r\n')
                else:
                    img = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(img, f"Verbinde zu {user}...", (20, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                    _, encoded = cv2.imencode('.jpg', img)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encoded) + b'\r\n')
                time.sleep(0.03)
        finally:
            if user in viewers_watching: viewers_watching.remove(user)
            if user in active_streams: del active_streams[user]
    return StreamingResponse(generate_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/verify")
def verify_license_endpoint(data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keys WHERE key_code = ? AND status = 'Aktiv'", (data.get("key", ""),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"success": True, "message": "Key validiert", "expiry": row[2]}
    return {"success": False, "message": "Ungültiger Key"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
