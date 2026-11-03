import os
import random
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="Assmar00 God-Mode Backend", version="1.0")

# CORS erlauben, damit das Panel reibungslos kommuniziert
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Modell für Client-Daten
class ClientData(BaseModel):
    desktop: str
    cpu: str
    game: str
    hwid: str
    ip: str = "127.0.0.1"
    custom_name: str = "Client"

# Lokaler Speicher für aktive Sessions (wird durch echte Clients befüllt)
active_clients_db = [
    {
        "desktop": "ASSMAR-PC",
        "cpu": "AMD Ryzen 7",
        "game": "Valorant / Fortnite",
        "hwid": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "ip": "84.115.x.x",
        "custom_name": "Main Rig"
    }
]

# 1. Startseite: Liefert deine admin.html direkt im Browser aus!
@app.get("/", response_class=HTMLResponse)
def serve_admin():
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>Fehler: admin.html wurde im Hauptverzeichnis des GitHub-Repositories nicht gefunden!</h3>"

# 2. Statistiken für das Dashboard
@app.get("/api/stats")
def get_stats():
    return {
        "active_clients": len(active_clients_db),
        "open_tickets": 2,
        "total_keys": 42
    }

# 3. Liste aller aktiven Benutzer/Sessions abrufen
@app.get("/api/users")
def get_users():
    return active_clients_db

# 4. Live Screen Video Feed (OpenCV / MSS Simulation für den Cloud-Server)
@app.get("/video_feed")
def video_feed(user: str = "Unknown", fps: int = 15, res: str = "720p"):
    def generate_dummy_stream():
        # Da Render in der Cloud läuft und keinen echten Monitor abgreifen kann,
        # streamt hier ein stabiler Platzhalter/Loop oder deine OpenCV-Logik.
        while True:
            # Platzhalter für Frame-Generation
            frame_data = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + b"\xff\xd8\xff\xe0\x00\x10JFIF" + random.randbytes(1024) + b"\r\n"
            yield frame_data
            
    return StreamingResponse(generate_dummy_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

# 5. Endpunkt für Clients, um sich zu registrieren/melden
@app.post("/api/client/heartbeat")
def client_heartbeat(data: ClientData):
    for client in active_clients_db:
        if client["desktop"] == data.desktop:
            client.update(data.dict())
            return {"status": "updated"}
    active_clients_db.append(data.dict())
    return {"status": "registered"}
