import os
import sqlite3
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Assmar00 God-Mode Complete Backend", version="4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQLite Datenbank initialisieren
DB_FILE = "database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Clients / Sessions Tabelle
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
    
    # Lizenz-Schlüssel Tabelle
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key_code TEXT PRIMARY KEY,
            note TEXT,
            expiry TEXT,
            status TEXT DEFAULT 'Aktiv'
        )
    """)
    
    # Tickets Tabelle
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            category TEXT,
            game TEXT,
            message TEXT,
            status TEXT DEFAULT 'Offen'
        )
    """)
    
    # Standard-Key einfügen, falls noch keiner existiert (damit du direkt testen kannst)
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

# 1. Admin-Panel direkt ausliefern
@app.get("/", response_class=HTMLResponse)
def serve_admin():
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>Fehler: admin.html wurde im GitHub-Repository nicht gefunden!</h3>"

# 2. Statistiken für das Dashboard
@app.get("/api/stats")
def get_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM clients")
    active_clients = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE status='Offen'")
    open_tickets = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM keys")
    total_keys = cursor.fetchone()[0]
    conn.close()
    
    return {
        "active_clients": active_clients,
        "open_tickets": open_tickets,
        "total_keys": total_keys
    }

# 3. Liste aller verbundenen User abrufen
@app.get("/api/users")
def get_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# 4. Heartbeat von echten Clients
@app.post("/api/client/heartbeat")
def client_heartbeat(data: ClientData):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    conn.close()
    return {"status": "success"}

# 5. Live Screen Video Feed
@app.get("/video_feed")
def video_feed(user: str):
    def generate_stream():
        while True:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients WHERE desktop=?", (user,))
            client = cursor.fetchone()
            conn.close()

            img = np.zeros((480, 640, 3), dtype=np.uint8)
            if client:
                cv2.putText(img, f"LIVE: {user}", (20, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                cv2.putText(img, f"CLIENT OFFLINE", (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            _, encoded = cv2.imencode('.jpg', img)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encoded) + b'\r\n')

    return StreamingResponse(generate_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

# 6. NEU: Key über das Admin-Panel erstellen / speichern
@app.post("/api/keys/create")
def create_key_api(data: dict):
    key_code = data.get("key_code")
    note = data.get("note", "")
    expiry = data.get("expiry", "2026-12-31")
    
    if not key_code:
        raise HTTPException(status_code=400, detail="Key Code fehlt")
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO keys (key_code, note, expiry, status)
        VALUES (?, ?, ?, 'Aktiv')
    """, (key_code, note, expiry))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Key {key_code} erfolgreich erstellt!"}

# 7. NEU: Alle Keys für das Panel abrufen
@app.get("/api/keys")
def get_keys():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keys")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# 8. NEU: Lizenz-Verifizierung für deinen Python-Loader (`firefox.py`)
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
