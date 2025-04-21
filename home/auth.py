from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class DiscordAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        try:
            # Check if this is a Discord user
            if username.startswith('discord_'):
                user = User.objects.get(username=username)
                # Get the numeric Discord ID
                discord_id = username.replace('discord_', '')
                print(f"\n=== Auth Backend Debug ===")
                print(f"Checking admin status for Discord ID: {discord_id}")
                print(f"Admin IDs from settings: {settings.DISCORD_ADMIN_IDS}")
                print(f"Current user is_staff: {user.is_staff}")
                print(f"Current user is_superuser: {user.is_superuser}")
                
                # Update admin status
                if discord_id in settings.DISCORD_ADMIN_IDS:
                    print("Granting admin privileges...")
                    user.is_staff = True
                    user.is_superuser = True
                    user.save()
                    print(f"Updated user is_staff: {user.is_staff}")
                    print(f"Updated user is_superuser: {user.is_superuser}")
                else:
                    print("User is not in admin list")
                    user.is_staff = False
                    user.is_superuser = False
                    user.save()
                
                print("=== End Auth Backend Debug ===\n")
                return user
        except User.DoesNotExist:
            return None
        return None
    
    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None 