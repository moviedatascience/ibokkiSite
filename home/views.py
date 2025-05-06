# home/views.py

import requests
from django.shortcuts import redirect, render
from django.conf import settings
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required
from .kick_api import get_channel_info
from .models import StreamSettings
from django.contrib import messages
from urllib.parse import urlparse, quote
from django.http import HttpResponseBadRequest, JsonResponse
import logging

logger = logging.getLogger(__name__)

def landing_page(request):
    """Landing page view"""
    # Get the featured stream (default)
    featured_stream = StreamSettings.objects.filter(is_featured=True, is_active=True).first()
    
    # If no featured stream, get any active stream
    if not featured_stream:
        featured_stream = StreamSettings.objects.filter(is_active=True).first()
    
    # Get channel info to check if stream is live
    if featured_stream:
        channel_data = get_channel_info(featured_stream.channel_slug)
        is_live = channel_data.get('is_live', False)
        title = channel_data.get('title', 'Error Checking Stream')
    else:
        is_live = False
        title = 'No Stream Available'
    
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
    
    # Debug logging
    logger.debug("Discord OAuth Debug", extra={
        'base_url': settings.BASE_URL,
        'redirect_uri': settings.DISCORD_REDIRECT_URI,
        'environment': settings.ENVIRONMENT,
        'debug_mode': settings.DEBUG
    })
    
    # Build the Discord OAuth2 URL with proper URL encoding
    oauth_url = (
        'https://discord.com/api/oauth2/authorize'
        f'?client_id={settings.DISCORD_CLIENT_ID}'
        f'&redirect_uri={quote(settings.DISCORD_REDIRECT_URI, safe="")}'
        '&response_type=code'
        '&scope=identify email'
    )
    logger.debug(f"Full OAuth URL: {oauth_url}")
    
    return redirect(oauth_url)

def discord_callback(request):
    code = request.GET.get('code')
    if not code:
        return HttpResponseBadRequest("No code provided")
    
    # Get the redirect URI from settings
    redirect_uri = settings.DISCORD_REDIRECT_URI
    
    # Debug logging
    logger.debug("Discord Callback Debug", extra={
        'code': code,
        'redirect_uri': redirect_uri,
        'request_params': dict(request.GET)
    })
    
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
        logger.debug("Token response", extra={
            'status_code': token_response.status_code,
            'response_body': token_response.text
        })
        
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
        
        # Create username from Discord username and discriminator
        username = f"{user_info['username']}#{user_info['discriminator']}"
        
        # Get or create user using the custom user model
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': user_info.get('email', ''),
                'first_name': user_info.get('username', ''),
                'display_name': user_info.get('username', ''),
            }
        )
        
        # Update user info
        user.email = user_info.get('email', '')
        user.first_name = user_info.get('username', '')
        if not user.display_name:
            user.display_name = user_info.get('username', '')
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
        
        logger.debug(f"Redirecting to: {next_url}")
        
        return redirect(next_url)
        
    except requests.RequestException as e:
        logger.error("Discord authentication error", extra={
            'error': str(e),
            'response_content': e.response.text if hasattr(e, 'response') else 'No response content'
        })
        return HttpResponseBadRequest("Failed to authenticate with Discord")

@login_required
def profile_view(request):
    """
    Profile page showing the current user's info with ability to change display name.
    """
    if request.method == 'POST':
        new_display_name = request.POST.get('display_name')
        if new_display_name:
            try:
                # Check if display name is already taken
                User = get_user_model()
                if User.objects.filter(display_name=new_display_name).exclude(pk=request.user.pk).exists():
                    messages.error(request, 'That display name is already taken.')
                else:
                    request.user.display_name = new_display_name
                    request.user.save()
                    messages.success(request, 'Display name updated successfully!')
            except Exception as e:
                messages.error(request, f'Error updating display name: {str(e)}')
    
    return render(request, "home/profile.html", {
        "user": request.user
    })

@login_required
def watch(request):
    # Get the featured stream (default)
    featured_stream = StreamSettings.objects.filter(is_featured=True).first()
    
    # Get all active streams
    active_streams = StreamSettings.objects.filter(is_active=True)
    
    # Get the selected stream from session or use featured
    selected_stream = request.session.get('selected_stream')
    if selected_stream:
        stream = StreamSettings.objects.filter(channel_slug=selected_stream).first()
        if not stream or not stream.is_active:
            stream = featured_stream
    else:
        stream = featured_stream
    
    context = {
        'stream_title': stream.channel_slug if stream else 'No Stream Available',
        'channel_slug': stream.channel_slug if stream else None,
        'embed_url': stream.get_embed_url() if stream else None,
        'active_streams': active_streams,
        'current_stream': stream.channel_slug if stream else None,
    }
    return render(request, 'home/watch.html', context)

def switch_stream(request):
    if request.method == 'POST' and request.user.is_authenticated:
        stream_slug = request.POST.get('stream_slug')
        if stream_slug:
            stream = StreamSettings.objects.filter(channel_slug=stream_slug, is_active=True).first()
            if stream:
                request.session['selected_stream'] = stream_slug
                return JsonResponse({'success': True, 'channel_slug': stream_slug})
    return JsonResponse({'success': False, 'error': 'Invalid request'})
