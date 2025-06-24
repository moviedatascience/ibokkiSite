from django.core.exceptions import ValidationError
from django.test import TestCase
from django.contrib.auth import get_user_model

from home.models import StreamSettings, ChatMessage, Emote

class StreamSettingsModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='admin', password='pass')

    def test_only_one_featured_stream(self):
        StreamSettings.objects.create(channel_slug='s1', platform='kick', is_featured=True, is_active=True, updated_by=self.user)
        stream = StreamSettings(channel_slug='s2', platform='kick', is_featured=True, is_active=True, updated_by=self.user)
        with self.assertRaises(ValidationError):
            stream.full_clean()

    def test_youtube_requires_channel_id(self):
        stream = StreamSettings(channel_slug='yt', platform='youtube', is_active=True, updated_by=self.user)
        with self.assertRaises(ValidationError):
            stream.full_clean()

    def test_str_representation(self):
        stream = StreamSettings.objects.create(channel_slug='s1', platform='kick', is_active=True, updated_by=self.user)
        self.assertIn('s1', str(stream))

class ChatMessageModelTests(TestCase):
    def test_chat_message_str(self):
        user = get_user_model().objects.create_user(username='u1', password='pass')
        msg = ChatMessage.objects.create(user=user, message='hello world')
        self.assertIn('hello world', str(msg))
