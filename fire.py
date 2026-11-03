import requests
import platform

def verify_loader():
    url = "http://127.0.0.1:8000/api/loader/auth"
    
    payload = {
        "key": "ASSMAR-TEST-KEY",
        "hwid": "e3b0c44298fc1c14...",
        "desktop_name": platform.node(),
        "cpu": platform.processor(),
        "game": "Fortnite"
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Erfolgreich mit God-Mode Server verbunden!")
            return True
        else:
            print("Zugriff verweigert!")
            return False
    except Exception as e:
        print("Server nicht erreichbar:", e)
        return False

if __name__ == "__main__":
    verify_loader()