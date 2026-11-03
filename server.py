import os
import sqlite3
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Assmar00 God-Mode Complete Backend", version="6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            desktop TEXT PRIMARY KEY,
            custom_name TEXT,
            hwid TEXT,
            ip TEXT,
            cpu TEXT,
            game TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            identifier TEXT PRIMARY KEY
        )
    """)
    
    # Standard-Einstellungen für Remote Features
    defaults = {
        "aimbot_allowed": "true",
        "stream_allowed": "true",
        "mass_command": "",
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
    game: str = "Idle"

@app.get("/", response_class=HTMLResponse)
def serve_admin():
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>Fehler: admin.html wurde im GitHub-Repository nicht gefunden!</h3>"

@app.get("/api/stats")
def get_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM clients")
    active_clients = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM keys")
    total_keys = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM bans")
    total_bans = cursor.fetchone()[0]
    conn.close()
    return {"active_clients": active_clients, "open_tickets": 0, "total_keys": total_keys, "total_bans": total_bans}

@app.get("/api/users")
def get_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# HEARTBEAT & VOLLSTÄNDIGER REMOTE-SYNC
@app.post("/api/client/heartbeat")
def client_heartbeat(data: ClientData):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Prüfen ob HWID oder IP gebannt ist
    cursor.execute("SELECT * FROM bans WHERE identifier=? OR identifier=?", (data.hwid, data.ip))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="Client is banned")

    cursor.execute("""
        INSERT INTO clients (desktop, custom_name, hwid, ip, cpu, game)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(desktop) DO UPDATE SET
        custom_name=excluded.custom_name,
        hwid=excluded.hwid,
        ip=excluded.ip,
        cpu=excluded.cpu,
        game=excluded.game,
        last_seen=CURRENT_TIMESTAMP
    """, (data.desktop, data.custom_name, data.hwid, data.ip, data.cpu, data.game))
    conn.commit()
    
    # Alle Remote-Einstellungen für den Loader auslesen
    cursor.execute("SELECT key, value FROM global_settings")
    settings_rows = cursor.fetchall()
    global_cfg = {row[0]: row[1] for row in settings_rows}
    
    conn.close()
    
    return {
        "status": "success",
        "settings": global_cfg
    }

@app.post("/api/settings/update")
def update_settings(data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for k, v in data.items():
        cursor.execute("""
            INSERT INTO global_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (k, str(v)))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Einstellungen synchronisiert!"}

@app.post("/api/bans/add")
def add_ban(data: dict):
    identifier = data.get("identifier")
    if not identifier:
        raise HTTPException(status_code=400, detail="Identifier fehlt")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO bans (identifier) VALUES (?)", (identifier,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"'{identifier}' wurde gesperrt!"}

@app.post("/api/keys/create")
def create_key_api(data: dict):
    key_code = data.get("key_code")
    note = data.get("note", "")
    expiry = data.get("expiry", "2026-12-31")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO keys (key_code, note, expiry, status) VALUES (?, ?, ?, 'Aktiv')", (key_code, note, expiry))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Key {key_code} erstellt!"}

@app.get("/api/keys")
def get_keys():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keys")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/verify")
def verify_license_endpoint(data: dict):
    key = data.get("key")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keys WHERE key_code=? AND status='Aktiv'", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"success": True, "message": "Key validiert", "expiry": row[2]}
    else:
        return {"success": False, "message": "Key existiert nicht oder ist abgelaufen"}
