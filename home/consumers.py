import json
import time
import asyncio
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
        
        # Extract stream identifier from URL path or query parameters
        url_route = self.scope.get('url_route', {})
        kwargs = url_route.get('kwargs', {}) if url_route else {}
        self.stream_id = kwargs.get('stream_id', 'general')
        
        # If no stream_id in URL, check query string
        if self.stream_id == 'general':
            query_string = self.scope.get('query_string', b'').decode()
            if 'stream=' in query_string:
                import urllib.parse
                params = urllib.parse.parse_qs(query_string)
                if 'stream' in params:
                    self.stream_id = params['stream'][0]
        
        self.room_name = f"stream_{self.stream_id}"
        self.room_group_name = f"chat_{self.room_name}"
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        print(f"WebSocket connection accepted for {self.scope['user']} in room {self.room_group_name}")
        
        # Send chat history for this specific stream
        await self.send_chat_history()
        
        # Initialize ping/pong keepalive
        self.last_ping = time.time()
        asyncio.create_task(self.keepalive_ping())

    async def disconnect(self, close_code):
        print(f"WebSocket disconnected for {self.scope['user']} from room {self.room_group_name}")
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        print(f"Received message from {self.scope['user']}: {text_data}")
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'message')
            
            # Handle different message types
            if message_type == 'ping':
                await self.handle_ping()
            elif message_type == 'pong':
                await self.handle_pong()
            elif message_type == 'command':
                command = text_data_json.get('command', '')
                await self.handle_command(command)
            elif message_type == 'message':
                message = text_data_json.get('message', '')
                await self.handle_message(message)
            elif message_type == 'join_stream':
                # Handle switching streams
                new_stream_id = text_data_json.get('stream_id', 'general')
                await self.switch_stream(new_stream_id)
            else:
                # Legacy support for old message format
                message = text_data_json.get('message', '')
                command = text_data_json.get('command', '')
                
                if command:
                    await self.handle_command(command)
                elif message:
                    await self.handle_message(message)
                    
        except json.JSONDecodeError as e:
            print(f"Error decoding message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Invalid message format'
            }))

    async def switch_stream(self, new_stream_id):
        """Handle switching to a different stream chat"""
        # Leave current room
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # Update room info
        self.stream_id = new_stream_id
        self.room_name = f"stream_{self.stream_id}"
        self.room_group_name = f"chat_{self.room_name}"
        
        # Join new room
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        print(f"User {self.scope['user']} switched to room {self.room_group_name}")
        
        # Send chat history for the new stream
        await self.send_chat_history()

    async def handle_ping(self):
        """Handle ping from client"""
        await self.send(text_data=json.dumps({
            'type': 'pong',
            'timestamp': time.time()
        }))

    async def handle_pong(self):
        """Handle pong from client"""
        self.last_ping = time.time()

    async def keepalive_ping(self):
        """Send periodic ping to client to maintain connection"""
        while True:
            try:
                await asyncio.sleep(30)  # Send ping every 30 seconds
                await self.send(text_data=json.dumps({
                    'type': 'ping',
                    'timestamp': time.time()
                }))
                
                # Check if client is still responding
                if time.time() - self.last_ping > 90:  # 90 seconds timeout
                    print(f"Client {self.scope['user']} ping timeout, closing connection")
                    await self.close()
                    break
                    
            except Exception as e:
                print(f"Keepalive error: {e}")
                break

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
                'type': 'error',
                'error': 'Message rate limit exceeded'
            }))
            return
        
        self.last_message_time = current_time
        
        # Validate message length
        if len(message) > settings.CHAT_MESSAGE_MAX_LENGTH:
            print(f"Message too long from {self.scope['user']}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Message too long'
            }))
            return
        
        # Get user info
        user = self.scope["user"]
        display_name = user.display_name or user.username

        # Save message to database with stream context
        chat_message = await database_sync_to_async(ChatMessage.objects.create)(
            user=user,
            message=message,
            stream_id=self.stream_id
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
                'stream_id': self.stream_id,
            }
        )

    async def handle_command(self, command):
        if not self.scope["user"].is_authenticated:
            return
        
        user = self.scope["user"]
        if not user.is_staff:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'You do not have permission to use commands'
            }))
            return
        
        # Handle mod commands here
        if command.startswith('/clear'):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_clear',
                    'stream_id': self.stream_id,
                }
            )
        elif command.startswith('/timeout'):
            # Parse timeout command: /timeout username duration
            parts = command.split()
            if len(parts) >= 2:
                username = parts[1]
                duration = int(parts[2]) if len(parts) > 2 else 300  # Default 5 minutes
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_timeout',
                        'username': username,
                        'duration': duration,
                        'stream_id': self.stream_id,
                    }
                )

    # Group message handlers
    async def chat_message(self, event):
        print(f"Broadcasting message: {event}")
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'user': event['user'],
            'user_id': event['user_id'],
            'is_staff': event['is_staff'],
            'timestamp': time.time(),
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    async def chat_clear(self, event):
        # Send clear command to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'clear',
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    async def user_timeout(self, event):
        # Send timeout notification to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'timeout',
            'username': event['username'],
            'duration': event['duration'],
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    @database_sync_to_async
    def get_chat_history(self):
        # Get the most recent N messages for this specific stream, newest last
        messages = ChatMessage.objects.select_related('user').filter(
            stream_id=self.stream_id
        ).order_by('-timestamp')[:settings.CHAT_MESSAGE_HISTORY_LENGTH]
        
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
                'stream_id': msg.stream_id,
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
            'type': 'history',
            'history': history,
            'stream_id': self.stream_id,
        })) 