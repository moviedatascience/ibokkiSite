import json
import time
import asyncio
import urllib.parse
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.conf import settings
from .models import ChatMessage, Emote, UserTimeout, UserBan, Poll, PollOption, PollVote
from django.utils.html import escape
from django.utils import timezone
from datetime import timedelta
from django.db import IntegrityError
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info(f"WebSocket connection attempt from {self.scope['user']}")

        url_route = self.scope.get('url_route', {})
        kwargs = url_route.get('kwargs', {}) if url_route else {}
        self.stream_id = kwargs.get('stream_id', 'general')

        if self.stream_id == 'general':
            query_string = self.scope.get('query_string', b'').decode()
            if 'stream=' in query_string:
                params = urllib.parse.parse_qs(query_string)
                if 'stream' in params:
                    self.stream_id = params['stream'][0]

        self.room_name = f"stream_{self.stream_id}"
        self.room_group_name = f"chat_{self.room_name}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(
            f"WebSocket connection accepted for {self.scope['user']} in room {self.room_group_name}"
        )

        await self.send_chat_history()

        # Send active poll if one exists
        await self.send_active_poll()

        self.last_ping = time.time()
        asyncio.create_task(self.keepalive_ping())

    async def disconnect(self, close_code):
        logger.info(
            f"WebSocket disconnected for {self.scope['user']} from room {self.room_group_name}"
        )
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        logger.info(f"Received message from {self.scope['user']}: {text_data}")
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'message')

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
                new_stream_id = text_data_json.get('stream_id', 'general')
                await self.switch_stream(new_stream_id)
            elif message_type == 'vote':
                poll_id = text_data_json.get('poll_id')
                option_id = text_data_json.get('option_id')
                await self.handle_vote(poll_id, option_id)
            else:
                message = text_data_json.get('message', '')
                command = text_data_json.get('command', '')

                if command:
                    await self.handle_command(command)
                elif message:
                    await self.handle_message(message)

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Invalid message format'
            }))

    async def switch_stream(self, new_stream_id):
        """Handle switching to a different stream chat"""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

        self.stream_id = new_stream_id
        self.room_name = f"stream_{self.stream_id}"
        self.room_group_name = f"chat_{self.room_name}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        logger.info(
            f"User {self.scope['user']} switched to room {self.room_group_name}"
        )

        await self.send_chat_history()
        await self.send_active_poll()

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
                await asyncio.sleep(30)
                await self.send(text_data=json.dumps({
                    'type': 'ping',
                    'timestamp': time.time()
                }))

                if time.time() - self.last_ping > 90:
                    logger.warning(
                        f"Client {self.scope['user']} ping timeout, closing connection"
                    )
                    await self.close()
                    break

            except Exception as e:
                logger.error(f"Keepalive error: {e}")
                break

    async def handle_message(self, message):
        if not self.scope["user"].is_authenticated:
            logger.warning(
                f"Unauthenticated user attempted to send message: {self.scope['user']}"
            )
            return

        message = message.strip()
        if not message:
            return

        user = self.scope["user"]

        # Check if user is banned
        is_banned = await database_sync_to_async(UserBan.is_banned)(user)
        if is_banned:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'You are banned from chat'
            }))
            return

        # Check if user is timed out in this stream
        is_timed_out = await database_sync_to_async(UserTimeout.is_timed_out)(user, self.stream_id)
        if is_timed_out:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'You are timed out'
            }))
            return

        # Rate limiting
        current_time = time.time()
        last_message_time = getattr(self, 'last_message_time', 0)
        if current_time - last_message_time < settings.CHAT_MESSAGE_RATE_LIMIT:
            logger.warning(f"Rate limit exceeded for {self.scope['user']}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Message rate limit exceeded'
            }))
            return

        self.last_message_time = current_time

        if len(message) > settings.CHAT_MESSAGE_MAX_LENGTH:
            logger.warning(f"Message too long from {self.scope['user']}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Message too long'
            }))
            return

        display_name = user.display_name or user.username

        await database_sync_to_async(ChatMessage.objects.create)(
            user=user,
            message=message,
            stream_id=self.stream_id
        )

        parsed_message = await self.parse_emotes(message)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': parsed_message,
                'user': display_name,
                'user_id': user.id,
                'role': user.role,
                'is_staff': user.is_staff,
                'stream_id': self.stream_id,
            }
        )

    async def handle_command(self, command):
        if not self.scope["user"].is_authenticated:
            return

        user = self.scope["user"]

        # Allow moderators and admins (by role or is_staff)
        if not user.is_moderator_or_above:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'You do not have permission to use commands'
            }))
            return

        cmd = command.split()[0] if command.split() else command

        if cmd == '/clear':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_clear',
                    'stream_id': self.stream_id,
                }
            )

        elif cmd == '/untimeout':
            await self._handle_untimeout_command(command, user)

        elif cmd == '/timeout':
            await self._handle_timeout_command(command, user)

        elif cmd == '/unban':
            await self._handle_unban_command(command, user)

        elif cmd == '/ban':
            await self._handle_ban_command(command, user)

        elif cmd == '/endpoll':
            await self._handle_endpoll_command(user)

        elif cmd == '/poll':
            await self._handle_poll_command(command, user)

    async def _handle_timeout_command(self, command, user):
        """Handle /timeout username [duration]"""
        parts = command.split()
        if len(parts) < 2:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Usage: /timeout username [seconds]'
            }))
            return

        username = parts[1]
        try:
            duration = int(parts[2]) if len(parts) > 2 else 300
        except ValueError:
            duration = 300

        target_user = await self._get_user_by_name(username)
        if not target_user:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'User "{username}" not found'
            }))
            return

        # Prevent timing out mods/admins
        if target_user.is_moderator_or_above:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Cannot timeout a moderator or admin'
            }))
            return

        await database_sync_to_async(UserTimeout.objects.create)(
            user=target_user,
            stream_id=self.stream_id,
            timed_out_by=user,
            expires_at=timezone.now() + timedelta(seconds=duration),
        )

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_timeout',
                'username': target_user.display_name or target_user.username,
                'duration': duration,
                'stream_id': self.stream_id,
            }
        )

    async def _handle_untimeout_command(self, command, user):
        """Handle /untimeout username"""
        parts = command.split()
        if len(parts) < 2:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Usage: /untimeout username'
            }))
            return

        username = parts[1]
        target_user = await self._get_user_by_name(username)
        if not target_user:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'User "{username}" not found'
            }))
            return

        await database_sync_to_async(UserTimeout.clear_timeout)(target_user, self.stream_id)

        await self.send(text_data=json.dumps({
            'type': 'info',
            'message': f'{username} timeout has been cleared'
        }))

    async def _handle_ban_command(self, command, user):
        """Handle /ban username [duration_hours]"""
        parts = command.split()
        if len(parts) < 2:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Usage: /ban username [duration_hours]'
            }))
            return

        username = parts[1]
        target_user = await self._get_user_by_name(username)
        if not target_user:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'User "{username}" not found'
            }))
            return

        if target_user.is_moderator_or_above:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Cannot ban a moderator or admin'
            }))
            return

        try:
            duration_hours = float(parts[2]) if len(parts) > 2 else None
        except ValueError:
            duration_hours = None

        is_permanent = duration_hours is None
        expires_at = None if is_permanent else timezone.now() + timedelta(hours=duration_hours)

        await database_sync_to_async(UserBan.objects.create)(
            user=target_user,
            banned_by=user,
            is_permanent=is_permanent,
            expires_at=expires_at,
        )

        display = target_user.display_name or target_user.username
        if is_permanent:
            ban_msg = f'{display} has been permanently banned'
        else:
            ban_msg = f'{display} has been banned for {duration_hours} hour(s)'

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_ban',
                'message': ban_msg,
                'stream_id': self.stream_id,
            }
        )

    async def _handle_unban_command(self, command, user):
        """Handle /unban username"""
        parts = command.split()
        if len(parts) < 2:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Usage: /unban username'
            }))
            return

        username = parts[1]
        target_user = await self._get_user_by_name(username)
        if not target_user:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'User "{username}" not found'
            }))
            return

        await database_sync_to_async(UserBan.clear_ban)(target_user)

        await self.send(text_data=json.dumps({
            'type': 'info',
            'message': f'{username} has been unbanned'
        }))

    async def _handle_poll_command(self, command, user):
        """Handle /poll [seconds] Question | Option1 | Option2 [| ...]"""
        content = command[len('/poll'):].strip()
        parts = [p.strip() for p in content.split('|')]

        if len(parts) < 3:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Usage: /poll [seconds] Question | Option1 | Option2 [| ...]'
            }))
            return

        # Check if the question part starts with a number (duration in seconds)
        question_part = parts[0]
        duration = 60
        tokens = question_part.split(None, 1)
        if len(tokens) >= 2 and tokens[0].isdigit():
            duration = max(10, min(int(tokens[0]), 600))
            question_part = tokens[1]
        elif len(tokens) == 1 and tokens[0].isdigit():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Usage: /poll [seconds] Question | Option1 | Option2 [| ...]'
            }))
            return

        question = question_part.strip()
        options = parts[1:]

        if not question:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Poll question cannot be empty'
            }))
            return

        if len(options) > 10:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Maximum 10 options per poll'
            }))
            return

        try:
            await self._deactivate_polls()
            poll_data = await self._create_poll(question, options, user, duration)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'poll_start',
                    'poll_id': poll_data['poll_id'],
                    'question': poll_data['question'],
                    'options': poll_data['options'],
                    'expires_at': poll_data['expires_at'],
                    'stream_id': self.stream_id,
                }
            )
        except Exception as e:
            logger.error(f"Poll creation failed: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'Failed to create poll: {e}'
            }))

    async def _handle_endpoll_command(self, user):
        """Handle /endpoll"""
        try:
            poll_data = await self._end_active_poll()

            if not poll_data:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'No active poll in this stream'
                }))
                return

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'poll_end',
                    'poll_id': poll_data['poll_id'],
                    'question': poll_data['question'],
                    'results': poll_data['results'],
                    'stream_id': self.stream_id,
                }
            )
        except Exception as e:
            logger.error(f"End poll failed: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'Failed to end poll: {e}'
            }))

    async def handle_vote(self, poll_id, option_id):
        """Handle a vote on a poll"""
        if not self.scope["user"].is_authenticated:
            return

        user = self.scope["user"]
        result = await self._record_vote(user, poll_id, option_id)

        if result.get('error'):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': result['error']
            }))
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'poll_update',
                'poll_id': result['poll_id'],
                'results': result['results'],
                'total_votes': result['total_votes'],
                'stream_id': self.stream_id,
            }
        )

    # --- Group message handlers ---

    async def chat_message(self, event):
        logger.info(f"Broadcasting message: {event}")
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'user': event['user'],
            'user_id': event['user_id'],
            'role': event.get('role', 'user'),
            'is_staff': event.get('is_staff', False),
            'timestamp': time.time(),
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    async def chat_clear(self, event):
        await self.send(text_data=json.dumps({
            'type': 'clear',
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    async def user_timeout(self, event):
        await self.send(text_data=json.dumps({
            'type': 'timeout',
            'username': event['username'],
            'duration': event['duration'],
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    async def user_ban(self, event):
        await self.send(text_data=json.dumps({
            'type': 'ban',
            'message': event['message'],
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    async def poll_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'poll_start',
            'poll_id': event['poll_id'],
            'question': event['question'],
            'options': event['options'],
            'expires_at': event['expires_at'],
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    async def poll_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'poll_update',
            'poll_id': event['poll_id'],
            'results': event['results'],
            'total_votes': event['total_votes'],
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    async def poll_end(self, event):
        await self.send(text_data=json.dumps({
            'type': 'poll_end',
            'poll_id': event['poll_id'],
            'question': event['question'],
            'results': event['results'],
            'stream_id': event.get('stream_id', self.stream_id),
        }))

    # --- Database helpers ---

    @database_sync_to_async
    def _get_user_by_name(self, username):
        """Look up a user by display_name or username."""
        try:
            return User.objects.get(display_name=username)
        except User.DoesNotExist:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist:
                return None

    @database_sync_to_async
    def _create_poll(self, question, option_texts, user, duration=60):
        """Create a new poll and return its serialized data."""
        poll = Poll.objects.create(
            stream_id=self.stream_id,
            question=question,
            created_by=user,
            expires_at=timezone.now() + timedelta(seconds=duration),
            is_active=True,
        )
        options = []
        for i, text in enumerate(option_texts):
            opt = PollOption.objects.create(poll=poll, text=text, order=i)
            options.append({'id': opt.id, 'text': opt.text, 'votes': 0})

        return {
            'poll_id': poll.id,
            'question': poll.question,
            'options': options,
            'expires_at': poll.expires_at.timestamp(),
        }

    @database_sync_to_async
    def _deactivate_polls(self):
        """Deactivate any active polls in this stream."""
        Poll.objects.filter(stream_id=self.stream_id, is_active=True).update(is_active=False)

    @database_sync_to_async
    def _end_active_poll(self):
        """End the active poll and return final results."""
        poll = Poll.objects.filter(stream_id=self.stream_id, is_active=True).first()
        if not poll:
            return None

        poll.is_active = False
        poll.save()

        results = []
        for opt in poll.options.all().order_by('order'):
            results.append({
                'id': opt.id,
                'text': opt.text,
                'votes': opt.votes.count(),
            })

        return {
            'poll_id': poll.id,
            'question': poll.question,
            'results': results,
        }

    @database_sync_to_async
    def _record_vote(self, user, poll_id, option_id):
        """Record a user's vote on a poll."""
        try:
            poll = Poll.objects.get(id=poll_id, is_active=True)
        except Poll.DoesNotExist:
            return {'error': 'This poll is no longer active'}

        try:
            option = PollOption.objects.get(id=option_id, poll=poll)
        except PollOption.DoesNotExist:
            return {'error': 'Invalid poll option'}

        try:
            PollVote.objects.create(poll=poll, option=option, user=user)
        except IntegrityError:
            return {'error': 'You have already voted on this poll'}

        # Build updated results
        results = []
        total_votes = 0
        for opt in poll.options.all().order_by('order'):
            count = opt.votes.count()
            total_votes += count
            results.append({
                'id': opt.id,
                'text': opt.text,
                'votes': count,
            })

        return {
            'poll_id': poll.id,
            'results': results,
            'total_votes': total_votes,
        }

    @database_sync_to_async
    def get_chat_history(self):
        messages = ChatMessage.objects.select_related('user').filter(
            stream_id=self.stream_id
        ).order_by('-timestamp')[:settings.CHAT_MESSAGE_HISTORY_LENGTH]

        emotes = {e.code: e.image.url for e in Emote.objects.all()}
        history = []
        for msg in reversed(messages):
            parsed_message = self._parse_emotes_sync(msg.message, emotes)
            history.append({
                'message': parsed_message,
                'user': msg.user.display_name or msg.user.username,
                'user_id': msg.user.id,
                'role': msg.user.role,
                'is_staff': msg.user.is_staff,
                'timestamp': msg.timestamp.timestamp(),
                'stream_id': msg.stream_id,
            })
        return history

    async def send_active_poll(self):
        """Send the active poll to the connecting client, if one exists."""
        poll_data = await self._get_active_poll_data()
        if poll_data:
            await self.send(text_data=json.dumps({
                'type': 'poll_start',
                'poll_id': poll_data['poll_id'],
                'question': poll_data['question'],
                'options': poll_data['options'],
                'expires_at': poll_data['expires_at'],
                'stream_id': self.stream_id,
            }))

    @database_sync_to_async
    def _get_active_poll_data(self):
        """Get the active poll for this stream, if any."""
        poll = Poll.get_active_poll(self.stream_id)
        if not poll:
            return None

        options = []
        total_votes = 0
        for opt in poll.options.all().order_by('order'):
            count = opt.votes.count()
            total_votes += count
            options.append({'id': opt.id, 'text': opt.text, 'votes': count})

        return {
            'poll_id': poll.id,
            'question': poll.question,
            'options': options,
            'expires_at': poll.expires_at.timestamp(),
        }

    async def parse_emotes(self, message):
        emotes = await database_sync_to_async(lambda: list(Emote.objects.all()))()
        emote_map = {e.code: e.image.url for e in emotes}
        return self._parse_emotes_sync(message, emote_map)

    def _parse_emotes_sync(self, message, emote_map):
        safe_message = escape(message)
        sorted_codes = sorted(emote_map.keys(), key=len, reverse=True)
        for code in sorted_codes:
            url = emote_map[code]
            safe_message = safe_message.replace(
                escape(code),
                f'<img src="{url}" alt="{code}" class="inline-emote" title="{code}">'
            )
        return safe_message

    async def send_chat_history(self):
        history = await self.get_chat_history()
        await self.send(text_data=json.dumps({
            'type': 'history',
            'history': history,
            'stream_id': self.stream_id,
        }))
