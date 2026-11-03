import os
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Assmar00 God-Mode Live Backend", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ClientData(BaseModel):
    desktop: str
    cpu: str
    game: str
    hwid: str
    ip: str = "127.0.0.1"
    custom_name: str = "Client"

# ECHTE Datenbank für verbundene Clients (Startet leer, füllt sich nur durch echte Clients)
active_clients_db = {}

@app.get("/", response_class=HTMLResponse)
def serve_admin():
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>admin.html nicht gefunden auf dem Server!</h3>"

@app.get("/api/stats")
def get_stats():
    return {
        "active_clients": len(active_clients_db),
        "open_tickets": 0,
        "total_keys": 1
    }

@app.get("/api/users")
def get_users():
    # Gibt nur die echten Clients zurück, die sich verbunden haben
    return list(active_clients_db.values())

@app.post("/api/client/heartbeat")
def client_heartbeat(data: ClientData):
    # Speichert oder aktualisiert den echten Client
    active_clients_db[data.desktop] = data.dict()
    return {"status": "connected"}

@app.get("/video_feed")
def video_feed(user: str, fps: int = 15, res: str = "720p"):
    def generate_real_stream():
        # Hier greift der Server den echten Stream des Clients ab (oder zeigt Warten-Bild, wenn Client offline ist)
        while True:
            if user in active_clients_db:
                # Platz für echten OpenCV / Screen Frame des Clients
                img = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(img, f"LIVE: {user}", (30, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            else:
                img = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(img, "CLIENT OFFLINE", (180, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            
            _, encoded = cv2.imencode('.jpg', img)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encoded) + b'\r\n')

    return StreamingResponse(generate_real_stream(), media_type="multipart/x-mixed-replace; boundary=frame")
