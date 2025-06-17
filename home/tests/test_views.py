from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from home.models import StreamSettings

class WatchViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='viewer', password='pass')
        self.client.force_login(self.user)

    def test_redirect_when_no_streams(self):
        response = self.client.get(reverse('watch'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('landing'))

    def test_success_with_featured_stream(self):
        StreamSettings.objects.create(channel_slug='stream1', platform='kick', is_featured=True, is_active=True, updated_by=self.user)
        response = self.client.get(reverse('watch'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'stream1')

class LandingViewTests(TestCase):
    def test_landing_page_loads(self):
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
