from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.conf import settings

# Create your models here.

class StreamSettings(models.Model):
    PLATFORM_CHOICES = [
        ('kick', 'Kick'),
        ('youtube', 'YouTube'),
        ('twitch', 'Twitch'),
    ]
    
    channel_slug = models.CharField(max_length=100, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default='kick')
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def clean(self):
        # Ensure only one stream is featured
        if self.is_featured:
            featured_streams = StreamSettings.objects.filter(is_featured=True).exclude(pk=self.pk)
            if featured_streams.exists():
                raise ValidationError("Only one stream can be featured at a time.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_embed_url(self):
        if self.platform == 'kick':
            return f"https://player.kick.com/{self.channel_slug}"
        elif self.platform == 'youtube':
            return f"https://www.youtube.com/embed/{self.channel_slug}"
        elif self.platform == 'twitch':
            return f"https://player.twitch.tv/?channel={self.channel_slug}&parent={settings.TWITCH_PARENT_DOMAIN}"
        return None

    def __str__(self):
        return f"{self.channel_slug} ({self.get_platform_display()}) [Featured: {self.is_featured}, Active: {self.is_active}]"
