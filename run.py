import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from werkzeug.serving import make_server

from money_manager import create_app


HOST = "127.0.0.1"
PORT = 5000
APP_URL = f"http://{HOST}:{PORT}"


def port_in_use(host=HOST, port=PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def money_manager_is_running():
    try:
        with urllib.request.urlopen(f"{APP_URL}/health", timeout=1) as response:
            payload = json.loads(response.read())
            return response.status == 200 and payload == {"app": "money-manager", "status": "ok"}
    except (OSError, ValueError, urllib.error.URLError):
        return False


def open_browser_when_ready():
    for _ in range(50):
        if money_manager_is_running():
            webbrowser.open(APP_URL)
            return
        time.sleep(0.1)


def browser_enabled():
    return os.environ.get("MONEY_MANAGER_NO_BROWSER") != "1"


if __name__ == "__main__":
    if port_in_use():
        if money_manager_is_running():
            if browser_enabled():
                webbrowser.open(APP_URL)
            raise SystemExit(0)
        raise SystemExit("Port 5000 is already in use by another program. Close it, then start Money Manager again.")

    app = create_app()
    from money_manager.services.scheduling import start_scheduler
    scheduler_stop = start_scheduler(app)
    server = make_server(HOST, PORT, app, threaded=True)
    if browser_enabled():
        threading.Thread(target=open_browser_when_ready, daemon=True).start()
    print(f"Money Manager is running at {APP_URL}")
    print("Keep this window open. Press Ctrl+C to stop Money Manager.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Money Manager...")
    finally:
        scheduler_stop.set()
        server.server_close()
