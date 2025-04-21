from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q

# Create your models here.

class StreamSettings(models.Model):
    channel_slug = models.CharField(max_length=100, default="qoqsik")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Stream Settings"
        constraints = [
            models.UniqueConstraint(
                fields=['is_active'],
                condition=Q(is_active=True),
                name='unique_active_stream'
            )
        ]

    def __str__(self):
        return f"Stream Settings (Channel: {self.channel_slug})"

    def save(self, *args, **kwargs):
        # If this stream is being set as active, deactivate all others
        if self.is_active:
            StreamSettings.objects.exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)
