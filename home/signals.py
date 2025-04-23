from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Set initial display name if not set
        if not instance.display_name and '#' in instance.username:
            instance.display_name = instance.username.split('#')[0]
            instance.save() 