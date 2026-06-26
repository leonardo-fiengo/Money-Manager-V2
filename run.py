from money_manager import create_app
import socket


def port_in_use(host="127.0.0.1", port=5000):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


if __name__ == "__main__":
    if port_in_use():
        raise SystemExit("Port 5000 is already in use. Stop the existing Flask server before starting another one.")
    create_app().run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
