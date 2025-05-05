from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Sets a Discord user as admin'

    def add_arguments(self, parser):
        parser.add_argument('discord_id', type=str, help='The Discord ID of the user')

    def handle(self, *args, **options):
        discord_id = options['discord_id']
        username = f"discord_{discord_id}"
        
        try:
            user = User.objects.get(username=username)
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Successfully set {username} as admin'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {username} not found')) 