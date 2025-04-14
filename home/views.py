# home/views.py

import requests
from django.shortcuts import redirect, render
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from .kick_api import get_channel_info

def landing_page(request):
    # If you want to show the real 'is_stream_live' and 'current_stream_title'
    # from the 'get_channel_info' call, uncomment these lines:
    """
    channel_slug = "qoqsik"
    channel_data = get_channel_info(channel_slug)
    is_stream_live = channel_data["is_live"]
    current_stream_title = channel_data["title"]
    """

    # For now, let's just pass some test data
    context = {
        "is_stream_live": True,
        "current_stream_title": "Test Stream Title"
    }
    return render(request, 'home/landing.html', context)

def discord_login(request):
    """
    Step 1: Redirect the user to Discord’s OAuth2 page.
    """
    base_auth_url = "https://discord.com/oauth2/authorize"
    scope = "identify email"  # or whichever scopes you need

    # Build query string
    import urllib.parse
    query_params = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "redirect_uri": settings.DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
    }
    query_str = urllib.parse.urlencode(query_params)

    discord_auth_url = f"{base_auth_url}?{query_str}"
    
    # If user selected "remember me", store it in session
    if request.GET.get("remember_me") == "1":
        request.session["remember_me"] = True

    return redirect(discord_auth_url)

def discord_callback(request):
    """
    Step 2: Discord redirects user back here with ?code=XYZ.
    We exchange code for an access token, fetch user info, create user, log in.
    """
    code = request.GET.get("code")
    if not code:
        return redirect("landing")

    token_url = "https://discord.com/api/oauth2/token"
    data = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "client_secret": settings.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.DISCORD_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    # Exchange the code for an access token
    resp = requests.post(token_url, data=data, headers=headers)
    resp.raise_for_status()
    token_data = resp.json()
    access_token = token_data.get("access_token")

    # Fetch user info from Discord
    user_info_url = "https://discord.com/api/users/@me"
    auth_header = {"Authorization": f"Bearer {access_token}"}
    user_resp = requests.get(user_info_url, headers=auth_header)
    user_resp.raise_for_status()
    discord_user = user_resp.json()

    # Example: {"id": "12345", "username": "Bob", "discriminator": "1234", "email": "bob@example.com", ...}
    discord_id = discord_user["id"]
    username = discord_user["username"]
    email = discord_user.get("email")

    # Create or get a Django user
    user, created = User.objects.get_or_create(username=f"discord_{discord_id}")
    if email:
        user.email = email
    user.save()

    # Log them in
    login(request, user)

    # If we want "Remember Me" to set a long session expiry, check session
    if request.session.get("remember_me"):
        # e.g. 30 days
        request.session.set_expiry(60 * 60 * 24 * 30)
    else:
        # Expires when browser closes
        request.session.set_expiry(0)

    return redirect("profile")  # Go to the profile page

@login_required
def profile_view(request):
    """
    A simple profile page showing the current user's info.
    """
    return render(request, "home/profile.html", {
        "user": request.user
    })
