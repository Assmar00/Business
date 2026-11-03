import os
import sqlite3
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import base64
import time

app = FastAPI(title="Assmar00 Replay Buffer Backend", version="23.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database.db"
saved_clips = {}

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
    """ )
    
    defaults = {
        "command": "none",
        "min_version": "1.0.0"
    }
    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO global_settings (key, value) VALUES (?, ?)", (k, v))
        
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

class ClipData(BaseModel):
    desktop: str
    clip_b64: str

@app.get("/", response_class=HTMLResponse)
def serve_admin():
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>Fehler: admin.html nicht gefunden!</h3>"

@app.get("/api/settings")
def get_settings():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM global_settings")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

@app.post("/api/settings")
def update_settings(data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for k, v in data.items():
        cursor.execute("INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)", (k, str(v)))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/users")
def get_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/stats")
def get_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM clients")
    active_clients = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM keys")
    total_keys = cursor.fetchone()[0]
    conn.close()
    return {
        "active_clients": active_clients,
        "open_tickets": 0,
        "total_keys": total_keys,
        "total_bans": 0
    }

@app.post("/api/client/heartbeat")
def client_heartbeat(data: ClientData):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO clients (desktop, custom_name, hwid, ip, cpu, gpu, motherboard, ram, os_build, game, license_key, expiry, fps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(desktop) DO UPDATE SET
        custom_name=excluded.custom_name,
        hwid=excluded.hwid,
        ip=excluded.ip,
        cpu=excluded.cpu,
        gpu=excluded.gpu,
        motherboard=excluded.motherboard,
        ram=excluded.ram,
        os_build=excluded.os_build,
        game=excluded.game,
        license_key=excluded.license_key,
        expiry=excluded.expiry,
        fps=excluded.fps,
        last_seen=CURRENT_TIMESTAMP
    """, (data.desktop, data.custom_name, data.hwid, data.ip, data.cpu, data.gpu, data.motherboard, data.ram, data.os_build, data.game, data.license_key, data.expiry, data.fps))
    conn.commit()

    cursor.execute("SELECT key, value FROM global_settings")
    settings_rows = cursor.fetchall()
    global_cfg = {row[0]: row[1] for row in settings_rows}
    conn.close()
    
    return {"status": "success", "settings": global_cfg}

@app.post("/api/client/clip")
def receive_clip(data: ClipData):
    if data.clip_b64:
        saved_clips[data.desktop] = data.clip_b64
    return {"status": "success"}

@app.get("/api/get_clip")
def get_clip(user: str):
    if user in saved_clips:
        return {"clip_b64": saved_clips[user]}
    return {"clip_b64": ""}

@app.post("/verify")
def verify_license_endpoint(data: dict):
    return {"success": True, "message": "Key validiert", "expiry": "2026-12-31"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
