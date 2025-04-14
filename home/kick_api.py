# home/kick_api.py
import requests
import time
from django.conf import settings  

# Our in-memory token cache
TOKEN_CACHE = {
    "access_token": None,
    "expires_at": 0
}

def get_client_credentials_token():
    """
    Obtain a bearer token from Kick using the client credentials flow.
    """
    # Instead of hard-coding, pull from settings
    client_id = settings.KICK_CLIENT_ID
    client_secret = settings.KICK_CLIENT_SECRET

    # Check if our cached token is still valid
    if TOKEN_CACHE["access_token"] and time.time() < TOKEN_CACHE["expires_at"]:
        return TOKEN_CACHE["access_token"]

    token_url = "https://kick.com/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "channel:read", 
    }

    try:
        resp = requests.post(token_url, data=data, timeout=10)
        resp.raise_for_status()
        token_data = resp.json()

        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)

        TOKEN_CACHE["access_token"] = access_token
        # Subtract a small buffer from the expiry to be safe
        TOKEN_CACHE["expires_at"] = time.time() + expires_in - 30

        return access_token

    except requests.RequestException as e:
        print("DEBUG: Error obtaining Kick token", e)
        return None


def get_channel_info(channel_slug):
    """
    Use the Bearer token to retrieve channel info from Kick's official channels endpoint.
    """
    access_token = get_client_credentials_token()
    if not access_token:
        return {"is_live": False, "title": "Offline (no token)"}

    channel_url = f"https://kick.com/api/v2/channels/{channel_slug}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    try:
        resp = requests.get(channel_url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        is_live = data.get("is_live", False)
        title = data.get("session_title", "N/A")

        return {"is_live": is_live, "title": title}

    except requests.RequestException as e:
        print("DEBUG: Error fetching channel info", e)
        return {"is_live": False, "title": "Offline (error)"}