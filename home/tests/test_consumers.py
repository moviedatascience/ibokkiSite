from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings
from django.contrib.auth import get_user_model

from ibokki.asgi import application
from home.models import ChatMessage

TEST_CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}

@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class ChatConsumerTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='wsuser', password='pass')

    def test_send_message_creates_chat_message(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, '/ws/chat/teststream/')
            communicator.scope['user'] = self.user
            connected, _ = await communicator.connect()
            assert connected

            # First response is chat history
            await communicator.receive_json_from()

            await communicator.send_json_to({'type': 'message', 'message': 'hello'})
            response = await communicator.receive_json_from()
            assert response['type'] == 'message'
            assert response['message'] == 'hello'

            await communicator.disconnect()

        async_to_sync(scenario)()
        self.assertTrue(ChatMessage.objects.filter(message='hello', stream_id='teststream').exists())
