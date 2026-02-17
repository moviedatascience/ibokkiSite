from django.db import models
from django.contrib.auth.models import User, AbstractUser
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.conf import settings
import requests
import json
import hashlib
import secrets
from datetime import timedelta
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('subscriber', 'Subscriber'),
        ('moderator', 'Moderator'),
        ('admin', 'Admin'),
    ]

    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=100, unique=True, null=True, blank=True)
    invites_remaining = models.PositiveIntegerField(default=2)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.username
        super().save(*args, **kwargs)

    @property
    def is_moderator_or_above(self):
        """Returns True if user is a moderator, admin, or Django staff."""
        return self.role in ('moderator', 'admin') or self.is_staff

    def can_invite(self):
        """Check if user can send an invitation."""
        if self.is_superuser or self.role == 'admin':
            return True
        return self.invites_remaining > 0


class Invitation(models.Model):
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invitations_sent'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['token_hash']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return f"Invite to {self.email} by {self.invited_by.username} ({'used' if self.used else 'pending'})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.used and not self.is_expired

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def create_invitation(cls, email, invited_by, expiry_hours=72):
        """Create a new invitation and return the raw token (shown only once)."""
        raw_token = secrets.token_urlsafe(48)
        token_hash = cls.hash_token(raw_token)
        invitation = cls.objects.create(
            email=email,
            token_hash=token_hash,
            invited_by=invited_by,
            expires_at=timezone.now() + timedelta(hours=expiry_hours),
        )
        return invitation, raw_token

    @classmethod
    def validate_token(cls, raw_token):
        """Validate a raw token and return the invitation if valid."""
        token_hash = cls.hash_token(raw_token)
        try:
            invitation = cls.objects.get(token_hash=token_hash)
            if invitation.is_valid:
                return invitation
        except cls.DoesNotExist:
            pass
        return None


class PasswordResetToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='password_reset_tokens'
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['token_hash']),
        ]

    def __str__(self):
        return f"Password reset for {self.user.username} ({'used' if self.used else 'pending'})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.used and not self.is_expired

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def create_token(cls, user, expiry_hours=1):
        """Create a new reset token and return the raw token (shown only once)."""
        # Invalidate any existing unused tokens for this user
        cls.objects.filter(user=user, used=False).update(used=True)
        raw_token = secrets.token_urlsafe(48)
        token_hash = cls.hash_token(raw_token)
        reset_token = cls.objects.create(
            user=user,
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(hours=expiry_hours),
        )
        return reset_token, raw_token

    @classmethod
    def validate_token(cls, raw_token):
        """Validate a raw token and return the token object if valid."""
        token_hash = cls.hash_token(raw_token)
        try:
            token_obj = cls.objects.get(token_hash=token_hash)
            if token_obj.is_valid:
                return token_obj
        except cls.DoesNotExist:
            pass
        return None

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
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

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
        if not kwargs.pop('skip_full_clean', False):
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
            
            logger.debug(f"Video {video_id} is not live, returning latest VOD")
            return video_id  # Return the latest video even if not live
            
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
    stream_id = models.CharField(max_length=100, default='general', help_text="Stream identifier for chat grouping")
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['stream_id', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.user.display_name or self.user.username}: {self.message[:30]} [{self.stream_id}]"

class Emote(models.Model):
    code = models.CharField(max_length=32, unique=True, help_text="Emote code, e.g. :OMEGALUL:")
    image = models.ImageField(upload_to="emotes/")
    is_animated = models.BooleanField(default=False)

    def __str__(self):
        return self.code


class UserTimeout(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='timeouts_received'
    )
    stream_id = models.CharField(max_length=100, default='general')
    timed_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='timeouts_given'
    )
    reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['user', 'stream_id', '-expires_at']),
        ]

    def __str__(self):
        return f"Timeout: {self.user.username} in {self.stream_id} until {self.expires_at}"

    @classmethod
    def is_timed_out(cls, user, stream_id):
        """Check if a user is currently timed out in a given stream."""
        return cls.objects.filter(
            user=user,
            stream_id=stream_id,
            expires_at__gt=timezone.now(),
        ).exists()

    @classmethod
    def clear_timeout(cls, user, stream_id):
        """Remove active timeouts for a user in a stream."""
        cls.objects.filter(
            user=user,
            stream_id=stream_id,
            expires_at__gt=timezone.now(),
        ).delete()


class UserBan(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bans_received'
    )
    banned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bans_given'
    )
    reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_permanent = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        if self.is_permanent:
            return f"Permanent ban: {self.user.username}"
        return f"Ban: {self.user.username} until {self.expires_at}"

    @classmethod
    def is_banned(cls, user):
        """Check if a user is currently banned."""
        return cls.objects.filter(
            user=user,
        ).filter(
            Q(is_permanent=True) | Q(expires_at__gt=timezone.now())
        ).exists()

    @classmethod
    def clear_ban(cls, user):
        """Remove all active bans for a user."""
        cls.objects.filter(
            user=user,
        ).filter(
            Q(is_permanent=True) | Q(expires_at__gt=timezone.now())
        ).delete()


class Poll(models.Model):
    stream_id = models.CharField(max_length=100, default='general')
    question = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='polls_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['stream_id', '-created_at']),
        ]

    def __str__(self):
        status = 'active' if self.is_active else 'ended'
        return f"Poll: {self.question[:50]} ({status})"

    @classmethod
    def get_active_poll(cls, stream_id):
        """Get the currently active poll for a stream, if any."""
        return cls.objects.filter(
            stream_id=stream_id,
            is_active=True,
        ).first()


class PollOption(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.poll.question[:30]} - {self.text}"

    @property
    def vote_count(self):
        return self.votes.count()


class PollVote(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='votes')
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='poll_votes'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['poll', 'user'], name='unique_vote_per_user'),
        ]

    def __str__(self):
        return f"{self.user.username} voted '{self.option.text}' on '{self.poll.question[:30]}'"
