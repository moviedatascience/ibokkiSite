import json
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.conf import settings
from .models import ChatMessage, Emote
from django.utils.html import escape
from django.utils.safestring import mark_safe

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print(f"WebSocket connection attempt from {self.scope['user']}")
        self.room_name = "chat"
        self.room_group_name = f"chat_{self.room_name}"
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        print(f"WebSocket connection accepted for {self.scope['user']}")
        
        # Send chat history
        await self.send_chat_history()

    async def disconnect(self, close_code):
        print(f"WebSocket disconnected for {self.scope['user']}")
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        print(f"Received message from {self.scope['user']}: {text_data}")
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json.get('message', '')
            command = text_data_json.get('command', '')
            
            if command:
                await self.handle_command(command)
            else:
                await self.handle_message(message)
        except json.JSONDecodeError as e:
            print(f"Error decoding message: {e}")
            await self.send(text_data=json.dumps({
                'error': 'Invalid message format'
            }))

    async def handle_message(self, message):
        if not self.scope["user"].is_authenticated:
            print(f"Unauthenticated user attempted to send message: {self.scope['user']}")
            return
        
        # Rate limiting
        current_time = time.time()
        last_message_time = getattr(self, 'last_message_time', 0)
        if current_time - last_message_time < settings.CHAT_MESSAGE_RATE_LIMIT:
            print(f"Rate limit exceeded for {self.scope['user']}")
            await self.send(text_data=json.dumps({
                'error': 'Message rate limit exceeded'
            }))
            return
        
        self.last_message_time = current_time
        
        # Validate message length
        if len(message) > settings.CHAT_MESSAGE_MAX_LENGTH:
            print(f"Message too long from {self.scope['user']}")
            await self.send(text_data=json.dumps({
                'error': 'Message too long'
            }))
            return
        
        # Get user info
        user = self.scope["user"]
        display_name = user.display_name or user.username

        # Save message to database
        chat_message = await database_sync_to_async(ChatMessage.objects.create)(
            user=user,
            message=message
        )

        # Parse emotes in the message
        parsed_message = await self.parse_emotes(message)

        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': parsed_message,
                'user': display_name,
                'user_id': user.id,
                'is_staff': user.is_staff,
            }
        )

    async def handle_command(self, command):
        if not self.scope["user"].is_authenticated:
            return
        
        user = self.scope["user"]
        if not user.is_staff:
            await self.send(text_data=json.dumps({
                'error': 'You do not have permission to use commands'
            }))
            return
        
        # Handle mod commands here
        if command.startswith('/clear'):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_clear',
                }
            )
        elif command.startswith('/timeout'):
            # Implement timeout logic
            pass

    async def chat_message(self, event):
        print(f"Broadcasting message: {event}")
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'user': event['user'],
            'user_id': event['user_id'],
            'is_staff': event['is_staff'],
            'timestamp': time.time(),
        }))

    async def chat_clear(self, event):
        # Send clear command to WebSocket
        await self.send(text_data=json.dumps({
            'command': 'clear',
        }))

    @database_sync_to_async
    def get_chat_history(self):
        # Get the most recent N messages, newest last
        messages = ChatMessage.objects.select_related('user').order_by('-timestamp')[:settings.CHAT_MESSAGE_HISTORY_LENGTH]
        emotes = {e.code: e.image.url for e in Emote.objects.all()}
        history = []
        for msg in reversed(messages):
            # Parse emotes for each message
            parsed_message = self._parse_emotes_sync(msg.message, emotes)
            history.append({
                'message': parsed_message,
                'user': msg.user.display_name or msg.user.username,
                'user_id': msg.user.id,
                'is_staff': msg.user.is_staff,
                'timestamp': msg.timestamp.timestamp(),
            })
        return history

    async def parse_emotes(self, message):
        # Get all emotes from DB
        emotes = await database_sync_to_async(lambda: list(Emote.objects.all()))()
        emote_map = {e.code: e.image.url for e in emotes}
        return self._parse_emotes_sync(message, emote_map)

    def _parse_emotes_sync(self, message, emote_map):
        # Replace emote codes with <img> tags
        safe_message = escape(message)
        for code, url in emote_map.items():
            safe_message = safe_message.replace(
                escape(code),
                f'<img src="{url}" alt="{code}" class="inline-emote" style="height:1.5em;vertical-align:middle;">'
            )
        return safe_message

    async def send_chat_history(self):
        history = await self.get_chat_history()
        await self.send(text_data=json.dumps({
            'history': history
        })) 