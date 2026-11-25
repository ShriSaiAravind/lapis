import os
import sys
import json
import time
import base64
import webbrowser
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, urlencode

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import BASE_DIR, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI

TOKEN_STORE = os.path.join(BASE_DIR, "spotify_tokens.json")
SCOPES = "user-modify-playback-state user-read-playback-state"

auth_code = {"value": None}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        auth_code["value"] = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h2>Spotify connected. You can close this tab.</h2></body></html>")

    def log_message(self, format, *args):
        pass


def main():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("Error: set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env first.")
        return

    auth_url = "https://accounts.spotify.com/authorize?" + urlencode({
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SCOPES,
    })

    print("Opening browser for Spotify login...")
    webbrowser.open(auth_url)

    server = HTTPServer(("127.0.0.1", 8888), CallbackHandler)
    print("Waiting for login + approval...")
    server.handle_request()

    if not auth_code["value"]:
        print("Error: no authorization code received.")
        return

    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {auth_header}"},
        data={
            "grant_type": "authorization_code",
            "code": auth_code["value"],
            "redirect_uri": SPOTIFY_REDIRECT_URI,
        },
    )

    if resp.status_code != 200:
        print(f"Error exchanging code for tokens: {resp.status_code} {resp.text}")
        return

    data = resp.json()
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(TOKEN_STORE, "w", encoding="utf-8") as f:
        json.dump({
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": time.time() + data.get("expires_in", 3600) - 60,
        }, f, indent=2)

    print(f"Spotify connected. Tokens saved to {TOKEN_STORE}")


if __name__ == "__main__":
    main()