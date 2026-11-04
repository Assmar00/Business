import os
import sqlite3
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import base64
import time

app = FastAPI(title="Assmar00 Control Panel", version="52.0")

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
pending_messages = {}
global_mass_command = None

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
        CREATE TABLE IF NOT EXISTS user_history (
            hwid TEXT PRIMARY KEY,
            desktop TEXT,
            ip TEXT,
            cpu TEXT,
            gpu TEXT,
            motherboard TEXT,
            ram TEXT,
            os_build TEXT,
            license_key TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banned_hwids (
            hwid TEXT PRIMARY KEY,
            ip TEXT DEFAULT '',
            desktop TEXT DEFAULT ''
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
            status TEXT DEFAULT 'Unbenutzt',
            bound_hwid TEXT DEFAULT ''
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO global_settings (key, value) VALUES ('min_version', '1.0.0')", ())
    cursor.execute("INSERT OR IGNORE INTO global_settings (key, value) VALUES ('update_url', 'https://github.com/')", ())
    cursor.execute("INSERT OR IGNORE INTO global_settings (key, value) VALUES ('maintenance_mode', 'off')", ())
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
    version: str = "1.0.0"

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
    cursor.execute("DELETE FROM clients WHERE (julianday('now') - julianday(last_seen)) * 86400 > 6")
    conn.commit()

    cursor.execute("SELECT * FROM clients")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/history")
def get_history():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_history ORDER BY last_seen DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/bans")
def get_bans():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM banned_hwids")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/settings")
def get_settings():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM global_settings")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

@app.post("/api/settings/update")
def update_settings(data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for k, v in data.items():
        cursor.execute("INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)", (k, str(v)))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/admin/mass_command")
def post_mass_command(data: dict):
    global global_mass_command
    global_mass_command = data.get("command")
    return {"status": "success", "command": global_mass_command}

@app.post("/api/admin/ban_user")
def ban_user(data: dict):
    desktop = data.get("desktop")
    hwid = data.get("hwid")
    ip = data.get("ip", "")
    target_val = data.get("target")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if desktop:
        cursor.execute("SELECT hwid, ip FROM clients WHERE desktop = ?", (desktop,))
        row = cursor.fetchone()
        if row:
            db_hwid, db_ip = row
            target_ban_hwid = db_hwid if db_hwid else desktop
            cursor.execute("INSERT OR REPLACE INTO banned_hwids (hwid, ip, desktop) VALUES (?, ?, ?)", (target_ban_hwid, db_ip, desktop))
        else:
            cursor.execute("INSERT OR REPLACE INTO banned_hwids (hwid, ip, desktop) VALUES (?, ?, ?)", (desktop, ip, desktop))
        cursor.execute("DELETE FROM clients WHERE desktop = ?", (desktop,))
    elif hwid:
        cursor.execute("INSERT OR REPLACE INTO banned_hwids (hwid, ip, desktop) VALUES (?, ?, ?)", (hwid, ip, ""))
    elif target_val:
        cursor.execute("INSERT OR REPLACE INTO banned_hwids (hwid, ip, desktop) VALUES (?, ?, ?)", (target_val, target_val, target_val))

    conn.commit()
    conn.close()

    if desktop in viewers_watching: viewers_watching.remove(desktop)
    if desktop in active_streams: del active_streams[desktop]

    return {"status": "banned"}

@app.post("/api/admin/unban_user")
def unban_user(data: dict):
    hwid = data.get("hwid")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM banned_hwids WHERE hwid = ? OR ip = ? OR desktop = ?", (hwid, hwid, hwid))
    conn.commit()
    conn.close()
    return {"status": "unbanned"}

@app.post("/api/admin/send_message")
def send_client_message(data: MessageData):
    pending_messages[data.desktop] = data.message
    return {"status": "success"}

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
    cursor.execute("INSERT OR REPLACE INTO keys (key_code, note, expiry, status, bound_hwid) VALUES (?, ?, ?, 'Unbenutzt', '')", 
                   (data.key_code, data.note, data.expiry))
    conn.commit()
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

@app.post("/api/keys/update_status")
def update_key_status(data: dict):
    key_code = data.get("key_code")
    status = data.get("status")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE keys SET status = ? WHERE key_code = ?", (status, key_code))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/keys/pause_all")
def pause_all_keys():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE keys SET status = 'Pausiert'")
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/keys/extend")
def extend_key(data: dict):
    key_code = data.get("key_code")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE keys SET expiry = datetime(expiry, '+1 day') WHERE key_code = ?", (key_code,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/keys/reset_hwid")
def reset_key_hwid(data: dict):
    key_code = data.get("key_code")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE keys SET bound_hwid = '', status = 'Unbenutzt' WHERE key_code = ?", (key_code,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/client/heartbeat")
def client_heartbeat(data: ClientData):
    global global_mass_command
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM global_settings WHERE key = 'maintenance_mode'")
    m_row = cursor.fetchone()
    if m_row and m_row[0] == "on":
        conn.close()
        return {"status": "maintenance"}

    cursor.execute("SELECT value FROM global_settings WHERE key = 'min_version'")
    row_v = cursor.fetchone()
    min_ver = row_v[0] if row_v else "1.0.0"

    cursor.execute("SELECT value FROM global_settings WHERE key = 'update_url'")
    row_u = cursor.fetchone()
    up_url = row_u[0] if row_u else ""

    if data.version < min_ver:
        conn.close()
        return {"status": "update_required", "update_url": up_url}

    cursor.execute("SELECT * FROM banned_hwids WHERE hwid = ? OR (ip = ? AND ip != '') OR desktop = ?", (data.hwid, data.ip, data.desktop))
    if cursor.fetchone():
        cursor.execute("DELETE FROM clients WHERE desktop = ?", (data.desktop,))
        conn.commit()
        conn.close()
        return {"status": "banned"}

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

    cursor.execute("""
        INSERT INTO user_history (hwid, desktop, ip, cpu, gpu, motherboard, ram, os_build, license_key, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(hwid) DO UPDATE SET
        desktop=excluded.desktop, ip=excluded.ip, cpu=excluded.cpu, gpu=excluded.gpu,
        motherboard=excluded.motherboard, ram=excluded.ram, os_build=excluded.os_build,
        license_key=excluded.license_key, last_seen=CURRENT_TIMESTAMP
    """, (data.hwid, data.desktop, data.ip, data.cpu, data.gpu, data.motherboard, data.ram, data.os_build, data.license_key))

    conn.commit()
    conn.close()
    
    alert_msg = pending_messages.pop(data.desktop, None)
    is_active = data.desktop in viewers_watching
    
    current_cmd = global_mass_command
    global_mass_command = None

    return {
        "status": "success", 
        "stream_active": is_active, 
        "alert_message": alert_msg, 
        "mass_command": current_cmd
    }

@app.post("/verify")
def verify_license_endpoint(data: dict):
    hwid = data.get("hwid", "")
    ip = data.get("ip", "")
    key = data.get("key", "")
    desktop = data.get("desktop", "")
    version = data.get("version", "1.0.0")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT value FROM global_settings WHERE key = 'maintenance_mode'")
    m_row = cursor.fetchone()
    if m_row and m_row[0] == "on":
        conn.close()
        return {"success": False, "message": "System under maintenance!"}

    cursor.execute("SELECT value FROM global_settings WHERE key = 'min_version'")
    row_v = cursor.fetchone()
    min_ver = row_v[0] if row_v else "1.0.0"

    if version < min_ver:
        conn.close()
        return {"success": False, "message": "Outdated! Update Required."}
    
    cursor.execute("SELECT * FROM banned_hwids WHERE hwid = ? OR (ip = ? AND ip != '') OR desktop = ?", (hwid, ip, desktop))
    if cursor.fetchone():
        conn.close()
        return {"success": False, "message": "Key is banned"}

    cursor.execute("SELECT * FROM keys WHERE key_code = ?", (key,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return {"success": False, "message": "Key doesn't exist"}
    
    if row[3] == 'Pausiert':
        conn.close()
        return {"success": False, "message": "Key is frozzen"}

    bound_hwid = row[4]
    if bound_hwid and bound_hwid != hwid:
        conn.close()
        return {"success": False, "message": "HWID Mismatch"}
    
    cursor.execute("UPDATE keys SET bound_hwid = ?, status = 'Aktiviert' WHERE key_code = ?", (hwid, key))
    conn.commit()

    expiry_date = row[2]
    conn.close()
    return {"success": True, "message": "Access Granted", "expiry": expiry_date}

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
                    cv2.putText(img, f"Connecting to {user}...", (20, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                    _, encoded = cv2.imencode('.jpg', img)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encoded) + b'\r\n')
                time.sleep(0.03)
        finally:
            if user in viewers_watching: viewers_watching.remove(user)
            if user in active_streams: del active_streams[user]
    return StreamingResponse(generate_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000)
