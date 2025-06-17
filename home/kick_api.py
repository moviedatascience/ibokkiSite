# home/kick_api.py
import requests
import time
from django.conf import settings
import re
import logging

logger = logging.getLogger(__name__)

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
        logger.error("Error obtaining Kick token", exc_info=e)
        return None


def get_channel_info(channel_slug):
    """
    Get information about a Kick channel.
    Returns a dictionary with channel information.
    """
    try:
        # Just return the channel slug and let the player handle everything
        return {
            'is_live': True,  # Let the player handle this
            'title': 'Live Stream',  # Let the player handle this
            'playback_url': f"https://player.kick.com/{channel_slug}"
        }
    except Exception as e:
        logger.error(f"Error getting channel info: {str(e)}")
        return {
            'is_live': True,  # Let the player handle this
            'title': 'Live Stream',  # Let the player handle this
            'playback_url': f"https://player.kick.com/{channel_slug}"
        }