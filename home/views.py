# home/views.py

import requests
from django.shortcuts import redirect, render
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from .kick_api import get_channel_info
from .models import StreamSettings
from django.contrib import messages
from urllib.parse import urlparse
from django.http import HttpResponseBadRequest

def landing_page(request):
    """Landing page view"""
    # Get the active stream settings
    try:
        settings = StreamSettings.objects.get(is_active=True)
        if not settings.channel_slug:
            raise StreamSettings.DoesNotExist
    except StreamSettings.DoesNotExist:
        # If no active stream exists or channel_slug is empty, show landing page
        return render(request, 'home/landing.html', {
            'is_authenticated': request.user.is_authenticated,
            'user': request.user
        })
    
    # Get channel info to check if stream is live
    channel_data = get_channel_info(settings.channel_slug)
    is_live = channel_data.get('is_live', False)
    title = channel_data.get('title', 'Error Checking Stream')
    
    context = {
        "is_stream_live": is_live,
        "current_stream_title": title,
        'is_authenticated': request.user.is_authenticated,
        'user': request.user
    }
    return render(request, 'home/landing.html', context)

def discord_login(request):
    """Handle Discord OAuth2 login"""
    if not settings.DISCORD_CLIENT_ID or not settings.DISCORD_CLIENT_SECRET:
        return HttpResponseBadRequest("Discord integration is not configured")
    
    # Get the next URL from the request
    next_url = request.GET.get('next', '/watch/')
    
    # Store the next URL in the session
    request.session['next'] = next_url
    
    # Build the Discord OAuth2 URL
    oauth_url = (
        'https://discord.com/api/oauth2/authorize'
        f'?client_id={settings.DISCORD_CLIENT_ID}'
        f'&redirect_uri={settings.DISCORD_REDIRECT_URI}'
        '&response_type=code'
        '&scope=identify email'
    )
    
    return redirect(oauth_url)

def discord_callback(request):
    code = request.GET.get('code')
    if not code:
        return HttpResponseBadRequest("No code provided")
    
    # Get the redirect URI from settings
    redirect_uri = settings.DISCORD_REDIRECT_URI
    
    # Exchange code for token
    data = {
        'client_id': settings.DISCORD_CLIENT_ID,
        'client_secret': settings.DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    }
    
    try:
        # Get access token
        token_response = requests.post('https://discord.com/api/oauth2/token', data=data)
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data['access_token']
        
        # Get user info
        user_response = requests.get('https://discord.com/api/users/@me', headers={
            'Authorization': f'Bearer {access_token}'
        })
        user_response.raise_for_status()
        user_info = user_response.json()
        
        # Store user info in session
        request.session['discord_user'] = user_info
        
        # Get or create user
        user, created = User.objects.get_or_create(
            username=f"discord_{user_info['id']}",
            defaults={
                'email': user_info.get('email', ''),
                'first_name': user_info.get('username', ''),
            }
        )
        
        # Update user info
        user.email = user_info.get('email', '')
        user.first_name = user_info.get('username', '')
        user.save()
        
        # Log in the user
        from home.auth import DiscordAuthBackend
        backend = DiscordAuthBackend()
        user.backend = f"{backend.__module__}.{backend.__class__.__name__}"
        login(request, user)
        
        # Get next URL from session or default to watch page
        next_url = request.session.pop('next', '/watch/')
        
        # Ensure the next URL is absolute
        if not next_url.startswith('http'):
            next_url = f"{settings.BASE_URL}{next_url}"
        
        return redirect(next_url)
        
    except requests.RequestException as e:
        print(f"Error during Discord authentication: {str(e)}")
        return HttpResponseBadRequest("Failed to authenticate with Discord")

@login_required
def profile_view(request):
    """
    A simple profile page showing the current user's info.
    """
    return render(request, "home/profile.html", {
        "user": request.user
    })

@login_required
def watch_view(request):
    """
    View for watching the stream with embedded chat.
    """
    # Get the active stream settings
    try:
        stream_settings = StreamSettings.objects.get(is_active=True)
        if not stream_settings.channel_slug:
            raise StreamSettings.DoesNotExist
    except StreamSettings.DoesNotExist:
        messages.error(request, "No active stream settings found.")
        return redirect('landing')
    
    # Get channel info to check if stream is live
    channel_data = get_channel_info(stream_settings.channel_slug)
    is_live = channel_data.get('is_live', False)
    title = channel_data.get('title', 'Error Checking Stream')
    
    # Get the player URL for the channel
    player_url = f"https://player.kick.com/{stream_settings.channel_slug}"
    
    context = {
        "channel_slug": stream_settings.channel_slug,
        "stream_title": title,
        "player_url": player_url,
        "is_live": is_live,
        "error_message": title if not is_live else None
    }
    return render(request, "home/watch.html", context)
