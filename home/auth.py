from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from .models import CustomUser
import logging

logger = logging.getLogger(__name__)

class DiscordAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # Get Discord user info from session
            discord_user = request.session.get('discord_user')
            if not discord_user:
                return None
                
            # Get the Discord ID
            discord_id = discord_user['id']
            
            # Get or create user with the new username format
            username = f"{discord_user['username']}#{discord_user['discriminator']}"
            user, created = CustomUser.objects.get_or_create(
                username=username,
                defaults={
                    'email': discord_user.get('email', ''),
                    'first_name': discord_user.get('username', ''),
                    'display_name': discord_user.get('username', ''),  # Set initial display name
                }
            )
            
            # Update user info
            user.email = discord_user.get('email', '')
            user.first_name = discord_user.get('username', '')
            
            # Check admin status
            logger.debug("=== Auth Backend Debug ===")
            logger.debug(f"Checking admin status for Discord ID: {discord_id}")
            logger.debug(f"Admin IDs from settings: {settings.DISCORD_ADMIN_IDS}")
            logger.debug(f"Current user is_staff: {user.is_staff}")
            logger.debug(f"Current user is_superuser: {user.is_superuser}")
            
            # Update admin status
            if discord_id in settings.DISCORD_ADMIN_IDS:
                logger.info("Granting admin privileges...")
                user.is_staff = True
                user.is_superuser = True
            else:
                logger.info("User is not in admin list")
                user.is_staff = False
                user.is_superuser = False
            
            user.save()
            logger.debug(f"Updated user is_staff: {user.is_staff}")
            logger.debug(f"Updated user is_superuser: {user.is_superuser}")
            logger.debug("=== End Auth Backend Debug ===")
            
            return user
            
        except Exception as e:
            logger.error(f"Error in DiscordAuthBackend: {str(e)}")
            return None
    
    def get_user(self, user_id):
        try:
            return CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            return None 