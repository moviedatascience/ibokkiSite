# home/kick_api.py
import requests
import time
from django.conf import settings  
import re

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
    Get information about a Kick channel.
    Returns a dictionary with channel information.
    """
    try:
        # Use a realistic browser User-Agent and headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"'
        }
        
        # Get the channel page to check if stream is live
        channel_url = f"https://kick.com/{channel_slug}"
        response = requests.get(channel_url, headers=headers)
        
        print(f"DEBUG: Channel Page Response Status: {response.status_code}")
        
        if response.status_code == 200:
            # Check if stream is live by looking for isLiveBroadcast in the page
            is_live = "isLiveBroadcast" in response.text
            
            # Try to get the stream title from the page
            title = "Live Stream"
            title_match = re.search(r'<title>(.*?)</title>', response.text)
            if title_match:
                title = title_match.group(1).split(' - ')[0]
            
            # Construct the stream URL using the format from StreamCompanion
            stream_url = f"https://fa723fc1b171.us-west-2.playback.live-video.net/api/video/v1/us-west-2.196233775518.channel.{channel_slug}.m3u8"
            
            return {
                "is_live": is_live,
                "title": title,
                "playback_url": stream_url
            }
        else:
            print(f"DEBUG: Channel Page Error: {response.status_code}")
            return {
                "is_live": False,
                "title": "Error Checking Stream",
                "playback_url": None
            }
        
    except Exception as e:
        print(f"DEBUG: Error in get_channel_info: {str(e)}")
        return {
            "is_live": False,
            "title": "Error Checking Stream",
            "playback_url": None
        }