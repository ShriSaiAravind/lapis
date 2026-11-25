import os
import json
import time
import base64
import difflib
import requests

from config import BASE_DIR, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

TOKEN_STORE = os.path.join(BASE_DIR, "spotify_tokens.json")


def load_tokens():
    if not os.path.exists(TOKEN_STORE):
        return None
    with open(TOKEN_STORE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tokens(data):
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(TOKEN_STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def refresh_access_token(refresh_token):
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {auth_header}"},
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    tokens = load_tokens() or {}
    tokens["access_token"] = data["access_token"]
    tokens["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    if "refresh_token" in data:  # Spotify doesn't always rotate it
        tokens["refresh_token"] = data["refresh_token"]
    save_tokens(tokens)
    return tokens["access_token"]


def get_valid_token():
    tokens = load_tokens()
    if not tokens or "refresh_token" not in tokens:
        return None, "Error: Spotify isn't connected yet. Run tools/spotify_auth_setup.py once to log in."
    if tokens.get("expires_at", 0) > time.time():
        return tokens["access_token"], None
    try:
        return refresh_access_token(tokens["refresh_token"]), None
    except requests.RequestException as e:
        return None, f"Error refreshing Spotify token: {str(e)}"


def spotify_request(method, url, token, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, url, headers=headers, timeout=10, **kwargs)


def get_active_device(token):
    devices_resp = spotify_request("GET", "https://api.spotify.com/v1/me/player/devices", token)
    devices = devices_resp.json().get("devices", []) if devices_resp.status_code == 200 else []
    active = next((d for d in devices if d.get("is_active")), None)
    return active["id"] if active else (devices[0]["id"] if devices else None)


def start_playback(token, device_id, context_uri=None, uris=None, retries=1):
    """Reliably start playback on a device. Directly calling
    /me/player/play on a device that isn't already an active playback
    session is flaky with Spotify's API — it often plays for a moment and
    then silently re-pauses as the client's stale local state syncs back
    over the server's new state. Explicitly transferring playback to the
    device first (a separate endpoint) is the documented reliable path,
    and we verify afterward and retry once if it still shows paused."""

    # 1. Transfer playback to the target device and ask it to start
    #    playing immediately — this "wakes" a device that wasn't already
    #    an active session, which a direct play call often fails to do.
    spotify_request(
        "PUT", "https://api.spotify.com/v1/me/player", token,
        json={"device_ids": [device_id], "play": True},
    )
    time.sleep(0.3)  # give the device a moment to register as active

    # 2. Now issue the actual play command with the track/context.
    body = {"uris": uris} if uris else {"context_uri": context_uri}
    play_resp = spotify_request(
        "PUT", "https://api.spotify.com/v1/me/player/play", token,
        params={"device_id": device_id},
        json=body,
    )

    if play_resp.status_code not in (200, 202, 204):
        return play_resp

    # 3. Verify it actually stuck — this is the step that catches the
    #    "played for a second then repaused" bug. If it's not actually
    #    playing a beat later, retry the whole sequence once.
    time.sleep(0.6)
    check_resp = spotify_request("GET", "https://api.spotify.com/v1/me/player", token)
    if check_resp.status_code == 200:
        state = check_resp.json() or {}
        if not state.get("is_playing") and retries > 0:
            return start_playback(token, device_id, context_uri=context_uri, uris=uris, retries=retries - 1)

    return play_resp


def search_best_track_match(token, query, limit=5):
    """Search Spotify and pick the closest-matching track by comparing each
    candidate's title against the query text, rather than blindly trusting
    result #1 — Spotify's relevance ranking occasionally surfaces something
    only loosely related (mood/genre-adjacent) instead of the literal song
    asked for, and that's silently wrong in a way neither the API call nor
    a plain top-result pick would ever flag.

    Returns (track_item, score, is_low_confidence) or (None, 0, False) if
    no results at all.
    """
    search = spotify_request(
        "GET", "https://api.spotify.com/v1/search", token,
        params={"q": query, "type": "track", "limit": limit},
    )
    if search.status_code != 200:
        return None, 0, False

    items = search.json().get("tracks", {}).get("items", [])
    if not items:
        return None, 0, False

    query_norm = query.lower().strip()
    best_item = None
    best_score = -1.0

    for item in items:
        title_norm = item["name"].lower()
        artists_norm = ", ".join(a["name"] for a in item["artists"]).lower()
        score = difflib.SequenceMatcher(None, query_norm, title_norm).ratio()
        if query_norm in f"{title_norm} {artists_norm}":
            score += 0.15  # literal substring match is a strong signal
        if score > best_score:
            best_score = score
            best_item = item

    is_low_confidence = best_score < 0.5
    return best_item, best_score, is_low_confidence


def play_song_on_spotify(query):
    """Search Spotify for a track and start playing it immediately on an
    active Spotify device. Requires Spotify Premium and Spotify already
    open somewhere (desktop app, web player, or phone).

    Args:
        query: Song name and/or artist, e.g. 'Blinding Lights The Weeknd'

    Returns:
        Confirmation message with the track that started playing, or an
        error message
    """
    token, err = get_valid_token()
    if err:
        return err

    track, score, low_confidence = search_best_track_match(token, query)
    if not track:
        return f"No Spotify results found for '{query}'"

    track_uri = track["uri"]
    track_name = track["name"]
    artist_name = ", ".join(a["name"] for a in track["artists"])

    device_id = get_active_device(token)
    if not device_id:
        return (
            f"Found '{track_name}' by {artist_name}, but no active Spotify device. "
            f"Open Spotify (desktop, web, or phone) and try again."
        )

    play_resp = start_playback(token, device_id, uris=[track_uri])

    if play_resp.status_code not in (200, 202, 204):
        return f"Error starting playback: {play_resp.status_code} {play_resp.text[:200]}"

    result = f"Now playing '{track_name}' by {artist_name} on Spotify"
    if low_confidence:
        result += f" — NOTE: this is a low-confidence match for '{query}', it may not be the right song, worth confirming with the user"
    return result


def queue_song_on_spotify(query):
    """Search Spotify for a track and add it to the end of the current
    playback queue, without interrupting what's currently playing.

    Args:
        query: Song name and/or artist, e.g. 'As It Was Harry Styles'

    Returns:
        Confirmation message with the track queued, or an error message
    """
    token, err = get_valid_token()
    if err:
        return err

    track, score, low_confidence = search_best_track_match(token, query)
    if not track:
        return f"No Spotify results found for '{query}'"

    track_name = track["name"]
    artist_name = ", ".join(a["name"] for a in track["artists"])

    device_id = get_active_device(token)
    if not device_id:
        return f"Found '{track_name}' by {artist_name}, but no active Spotify device. Open Spotify first."

    queue_resp = spotify_request(
        "POST", "https://api.spotify.com/v1/me/player/queue", token,
        params={"uri": track["uri"], "device_id": device_id},
    )
    if queue_resp.status_code not in (200, 202, 204):
        return f"Error queuing track: {queue_resp.status_code} {queue_resp.text[:200]}"

    result = f"Queued '{track_name}' by {artist_name}"
    if low_confidence:
        result += f" — NOTE: this is a low-confidence match for '{query}', it may not be the right song, worth confirming with the user"
    return result


def play_playlist_on_spotify(query):
    """Search Spotify for a playlist and start playing it immediately on an
    active Spotify device. Requires Spotify Premium and Spotify already
    open somewhere.

    Args:
        query: Playlist name or vibe, e.g. 'Rap Caviar' or 'lofi beats'

    Returns:
        Confirmation message with the playlist that started playing, or an
        error message
    """
    token, err = get_valid_token()
    if err:
        return err

    search = spotify_request(
        "GET", "https://api.spotify.com/v1/search", token,
        params={"q": query, "type": "playlist", "limit": 1},
    )
    if search.status_code != 200:
        return f"Error searching Spotify: {search.status_code} {search.text[:200]}"

    items = search.json().get("playlists", {}).get("items", [])
    if not items:
        return f"No Spotify playlists found for '{query}'"

    playlist = items[0]
    playlist_uri = playlist["uri"]
    playlist_name = playlist["name"]
    owner = playlist.get("owner", {}).get("display_name", "")

    device_id = get_active_device(token)
    if not device_id:
        return f"Found playlist '{playlist_name}', but no active Spotify device. Open Spotify first."

    play_resp = start_playback(token, device_id, context_uri=playlist_uri)

    if play_resp.status_code not in (200, 202, 204):
        return f"Error starting playlist: {play_resp.status_code} {play_resp.text[:200]}"

    return f"Now playing playlist '{playlist_name}'" + (f" by {owner}" if owner else "")


def pause_spotify():
    """Pause whatever is currently playing on Spotify.

    Returns:
        Confirmation message or error
    """
    token, err = get_valid_token()
    if err:
        return err
    resp = spotify_request("PUT", "https://api.spotify.com/v1/me/player/pause", token)
    if resp.status_code not in (200, 202, 204):
        return f"Error pausing: {resp.status_code} {resp.text[:200]}"
    return "Paused Spotify playback"


def skip_spotify():
    """Skip to the next track on Spotify.

    Returns:
        Confirmation message or error
    """
    token, err = get_valid_token()
    if err:
        return err
    resp = spotify_request("POST", "https://api.spotify.com/v1/me/player/next", token)
    if resp.status_code not in (200, 202, 204):
        return f"Error skipping track: {resp.status_code} {resp.text[:200]}"
    return "Skipped to next track"