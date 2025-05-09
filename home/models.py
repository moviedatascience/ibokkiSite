from django.db import models
from django.contrib.auth.models import User, AbstractUser
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.conf import settings
import requests
import json
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class CustomUser(AbstractUser):
    display_name = models.CharField(max_length=100, unique=True, null=True, blank=True)
    
    def save(self, *args, **kwargs):
        # If display_name is not set, use the username without the discriminator
        if not self.display_name and '#' in self.username:
            self.display_name = self.username.split('#')[0]
        super().save(*args, **kwargs)

# Create your models here.

class StreamSettings(models.Model):
    PLATFORM_CHOICES = [
        ('kick', 'Kick'),
        ('youtube', 'YouTube'),
        ('twitch', 'Twitch'),
    ]
    
    channel_slug = models.CharField(max_length=100, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default='kick')
    youtube_channel_id = models.CharField(max_length=100, blank=True, null=True, help_text="Required for YouTube streams. Find in channel URL.")
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def clean(self):
        # Ensure only one stream is featured
        if self.is_featured:
            featured_streams = StreamSettings.objects.filter(is_featured=True).exclude(pk=self.pk)
            if featured_streams.exists():
                raise ValidationError("Only one stream can be featured at a time.")
        
        # Ensure YouTube channel ID is provided for YouTube streams
        if self.platform == 'youtube' and not self.youtube_channel_id:
            raise ValidationError("YouTube channel ID is required for YouTube streams.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_youtube_live_stream_id(self):
        """Fetch the current live stream ID for a YouTube channel"""
        if not self.youtube_channel_id or not settings.YOUTUBE_API_KEY:
            logger.debug(f"Missing YouTube channel ID or API key for {self.channel_slug}")
            return None
            
        try:
            # Handle both @handle and channel ID formats
            if self.youtube_channel_id.startswith('@'):
                # For @handle format, first get the channel ID
                handle = self.youtube_channel_id[1:]  # Remove the @
                logger.debug(f"Fetching channel ID for handle @{handle}")
                channel_url = f"https://www.googleapis.com/youtube/v3/search?part=id&type=channel&q={handle}&key={settings.YOUTUBE_API_KEY}"
                channel_response = requests.get(channel_url)
                channel_data = channel_response.json()
                
                if 'items' not in channel_data or not channel_data['items']:
                    logger.debug(f"No channel found for handle @{handle}")
                    return None
                    
                channel_id = channel_data['items'][0]['id']['channelId']
                logger.debug(f"Found channel ID {channel_id} for handle @{handle}")
            else:
                # For direct channel ID format
                channel_id = self.youtube_channel_id
                logger.debug(f"Using direct channel ID {channel_id}")
            
            # Get the uploads playlist ID
            logger.debug(f"Fetching uploads playlist for channel {channel_id}")
            channel_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={channel_id}&key={settings.YOUTUBE_API_KEY}"
            channel_response = requests.get(channel_url)
            channel_data = channel_response.json()
            
            if 'items' not in channel_data or not channel_data['items']:
                logger.debug(f"No channel data found for ID {channel_id}")
                return None
                
            uploads_playlist_id = channel_data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            logger.debug(f"Found uploads playlist {uploads_playlist_id}")
            
            # Get the latest video from the uploads playlist
            logger.debug(f"Fetching latest video from playlist {uploads_playlist_id}")
            playlist_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_playlist_id}&maxResults=1&key={settings.YOUTUBE_API_KEY}"
            playlist_response = requests.get(playlist_url)
            playlist_data = playlist_response.json()
            
            if 'items' not in playlist_data or not playlist_data['items']:
                logger.debug(f"No videos found in playlist {uploads_playlist_id}")
                return None
                
            video_id = playlist_data['items'][0]['snippet']['resourceId']['videoId']
            logger.debug(f"Found video ID {video_id}")
            
            # Check if this video is currently live
            logger.debug(f"Checking if video {video_id} is live")
            video_url = f"https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id={video_id}&key={settings.YOUTUBE_API_KEY}"
            video_response = requests.get(video_url)
            video_data = video_response.json()
            
            if ('items' in video_data and 
                video_data['items'] and 
                'liveStreamingDetails' in video_data['items'][0]):
                logger.debug(f"Video {video_id} is live")
                return video_id
                
            logger.debug(f"Video {video_id} is not live")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching YouTube live stream for {self.channel_slug}: {str(e)}")
            return None

    def get_embed_url(self):
        if self.platform == 'kick':
            return f"https://player.kick.com/{self.channel_slug}"
        elif self.platform == 'youtube':
            # Try to get the current live stream ID
            live_stream_id = self.get_youtube_live_stream_id()
            if live_stream_id:
                # Add origin parameter for local development
                origin = 'http://localhost:8000' if settings.ENVIRONMENT == 'local' else settings.BASE_URL
                return f"https://www.youtube.com/embed/{live_stream_id}?origin={origin}&autoplay=1&mute=1"
            # If no live stream, return None
            return None
        elif self.platform == 'twitch':
            # Use the parent domain from settings
            return f"https://player.twitch.tv/?channel={self.channel_slug}&parent={settings.TWITCH_PARENT_DOMAIN}"
        return None

    def __str__(self):
        return f"{self.channel_slug} ({self.get_platform_display()}) [Featured: {self.is_featured}, Active: {self.is_active}]"

class ChatMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.display_name or self.user.username}: {self.message[:30]}"

class Emote(models.Model):
    code = models.CharField(max_length=32, unique=True, help_text="Emote code, e.g. :OMEGALUL:")
    image = models.ImageField(upload_to="emotes/")
    is_animated = models.BooleanField(default=False)

    def __str__(self):
        return self.code
