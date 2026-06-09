# home/views.py

import time
from django.shortcuts import redirect, render
from django.conf import settings
from django.contrib.auth import login, authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import StreamSettings, Invitation, PasswordResetToken, Emote
from django.contrib import messages
from django.http import JsonResponse
import logging
from django.core.serializers.json import DjangoJSONEncoder
import json

logger = logging.getLogger(__name__)

User = get_user_model()

# ---------------------------------------------------------------------------
# Rate limiting helpers (in-memory, per-process)
# ---------------------------------------------------------------------------
_login_attempts = {}   # ip -> [timestamp, ...]
_reset_attempts = {}   # ip -> [timestamp, ...]

LOGIN_RATE_LIMIT = 5       # max attempts
LOGIN_RATE_WINDOW = 300    # per 5 minutes
RESET_RATE_LIMIT = 3       # max attempts
RESET_RATE_WINDOW = 600    # per 10 minutes


def _is_rate_limited(store, ip, limit, window):
    now = time.time()
    attempts = store.get(ip, [])
    # Remove old attempts
    attempts = [t for t in attempts if now - t < window]
    store[ip] = attempts
    if len(attempts) >= limit:
        return True
    attempts.append(now)
    store[ip] = attempts
    return False


# ---------------------------------------------------------------------------
# Login View (site entry point for unauthenticated users)
# ---------------------------------------------------------------------------
def login_view(request):
    """Login page -- the first page unauthenticated users see."""
    if request.user.is_authenticated:
        return redirect('landing')

    if request.method == 'POST':
        ip = request.META.get('REMOTE_ADDR', '')
        if _is_rate_limited(_login_attempts, ip, LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW):
            messages.error(request, 'Too many login attempts. Please try again later.')
            return render(request, 'home/login.html')

        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        remember_me = request.POST.get('remember_me')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if not remember_me:
                request.session.set_expiry(0)  # Session expires when browser closes
            next_url = request.GET.get('next', '/home/')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'home/login.html')


# ---------------------------------------------------------------------------
# Registration View (invite-based)
# ---------------------------------------------------------------------------
def register_view(request, token):
    """Registration page -- accessed via an invitation link."""
    if request.user.is_authenticated:
        return redirect('landing')

    invitation = Invitation.validate_token(token)
    if not invitation:
        return render(request, 'home/register.html', {
            'invalid_token': True,
        })

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        errors = []

        if not username:
            errors.append('Username is required.')
        elif User.objects.filter(username=username).exists():
            errors.append('That username is already taken.')

        if password != password_confirm:
            errors.append('Passwords do not match.')

        if not errors:
            try:
                validate_password(password)
            except ValidationError as e:
                errors.extend(e.messages)

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'home/register.html', {
                'invitation': invitation,
                'username': username,
            })

        # Create the user
        user = User.objects.create_user(
            username=username,
            email=invitation.email,
            password=password,
        )
        user.save()

        # Mark invitation as used
        from django.utils import timezone
        invitation.used = True
        invitation.used_at = timezone.now()
        invitation.save()

        # Decrement inviter's remaining invites (if not superuser)
        inviter = invitation.invited_by
        if not inviter.is_superuser and inviter.invites_remaining > 0:
            inviter.invites_remaining -= 1
            inviter.save()

        messages.success(request, 'Account created successfully! You can now log in.')
        return redirect('login')

    return render(request, 'home/register.html', {
        'invitation': invitation,
    })


# ---------------------------------------------------------------------------
# Invite View
# ---------------------------------------------------------------------------
@login_required
def send_invite_view(request):
    """Send an invitation email to a new user."""
    user = request.user

    if request.method == 'POST':
        if not user.can_invite():
            messages.error(request, 'You have no invitations remaining.')
            return redirect('invite')

        email = request.POST.get('email', '').strip().lower()
        if not email:
            messages.error(request, 'Please enter an email address.')
            return redirect('invite')

        # Check if email already has an active invitation or existing account
        if User.objects.filter(email=email).exists():
            messages.error(request, 'An account with this email already exists.')
            return redirect('invite')

        from django.utils import timezone as tz
        active_invite = Invitation.objects.filter(
            email=email, used=False
        ).exclude(
            expires_at__lt=tz.now()
        ).first()
        if active_invite:
            messages.error(request, 'An active invitation for this email already exists.')
            return redirect('invite')

        # Create invitation
        invitation, raw_token = Invitation.create_invitation(email=email, invited_by=user)

        # Build the registration URL
        register_url = f"{settings.BASE_URL}/register/{raw_token}/"

        # Send the email
        subject = 'You have been invited to Ibokki'
        message_body = render_to_string('home/email/invitation_email.txt', {
            'inviter': user.display_name or user.username,
            'register_url': register_url,
            'expiry_hours': 72,
        })
        try:
            send_mail(
                subject,
                message_body,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            messages.success(request, f'Invitation sent to {email}!')
        except Exception as e:
            logger.error(f"Failed to send invitation email to {email}: {e}")
            messages.error(request, 'Failed to send invitation email. Please try again.')
            # Clean up the invitation if email failed
            invitation.delete()
            if not user.is_superuser:
                # Don't decrement if email failed -- invite was cleaned up
                pass

        return redirect('invite')

    # GET: show invite form
    invitations = Invitation.objects.filter(invited_by=user).order_by('-created_at')[:20]
    context = {
        'invites_remaining': 'Unlimited' if user.is_superuser else user.invites_remaining,
        'invitations': invitations,
        'is_superuser': user.is_superuser,
    }
    return render(request, 'home/invite.html', context)


# ---------------------------------------------------------------------------
# Forgot Password View
# ---------------------------------------------------------------------------
def forgot_password_view(request):
    """Forgot password -- user enters their email to receive a reset link."""
    if request.user.is_authenticated:
        return redirect('landing')

    if request.method == 'POST':
        ip = request.META.get('REMOTE_ADDR', '')
        if _is_rate_limited(_reset_attempts, ip, RESET_RATE_LIMIT, RESET_RATE_WINDOW):
            messages.error(request, 'Too many reset requests. Please try again later.')
            return render(request, 'home/forgot_password.html')

        email = request.POST.get('email', '').strip().lower()

        # Always show the same message to prevent email enumeration
        messages.success(
            request,
            'If an account with that email exists, a password reset link has been sent.'
        )

        if email:
            try:
                user = User.objects.get(email=email)
                reset_token_obj, raw_token = PasswordResetToken.create_token(user)

                reset_url = f"{settings.BASE_URL}/reset-password/{raw_token}/"

                subject = 'Password Reset - Ibokki'
                message_body = render_to_string('home/email/password_reset_email.txt', {
                    'username': user.username,
                    'reset_url': reset_url,
                    'expiry_hours': 1,
                })
                send_mail(
                    subject,
                    message_body,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=True,
                )
            except User.DoesNotExist:
                pass  # Silently ignore -- don't leak whether the email exists
            except Exception as e:
                logger.error(f"Error during password reset for {email}: {e}")

        return redirect('forgot_password')

    return render(request, 'home/forgot_password.html')


# ---------------------------------------------------------------------------
# Reset Password View
# ---------------------------------------------------------------------------
def reset_password_view(request, token):
    """Reset password using a token from email."""
    if request.user.is_authenticated:
        return redirect('landing')

    token_obj = PasswordResetToken.validate_token(token)
    if not token_obj:
        return render(request, 'home/reset_password.html', {
            'invalid_token': True,
        })

    if request.method == 'POST':
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        errors = []

        if password != password_confirm:
            errors.append('Passwords do not match.')

        if not errors:
            try:
                validate_password(password, user=token_obj.user)
            except ValidationError as e:
                errors.extend(e.messages)

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'home/reset_password.html', {
                'token': token,
            })

        # Set new password
        token_obj.user.set_password(password)
        token_obj.user.save()

        # Mark token as used
        token_obj.used = True
        token_obj.save()

        messages.success(request, 'Your password has been reset. You can now log in.')
        return redirect('login')

    return render(request, 'home/reset_password.html', {
        'token': token,
    })


# ---------------------------------------------------------------------------
# Landing Page (requires login now)
# ---------------------------------------------------------------------------
@login_required
def landing_page(request):
    """Landing page view -- shown after login."""
    featured_stream = StreamSettings.objects.filter(is_featured=True, is_active=True).first()

    if not featured_stream:
        featured_stream = StreamSettings.objects.filter(is_active=True).first()

    if featured_stream:
        title = featured_stream.channel_slug
    else:
        title = 'No Stream Available'

    context = {
        "current_stream_title": title,
        'user': request.user
    }
    return render(request, 'home/landing.html', context)


# ---------------------------------------------------------------------------
# Profile View
# ---------------------------------------------------------------------------
@login_required
def profile_view(request):
    """Profile page showing the current user's info with ability to change display name."""
    if request.method == 'POST':
        new_display_name = request.POST.get('display_name')
        if new_display_name:
            try:
                if User.objects.filter(display_name=new_display_name).exclude(pk=request.user.pk).exists():
                    messages.error(request, 'That display name is already taken.')
                else:
                    request.user.display_name = new_display_name
                    request.user.save()
                    messages.success(request, 'Display name updated successfully!')
            except Exception as e:
                messages.error(request, f'Error updating display name: {str(e)}')

    return render(request, "home/profile.html", {
        "user": request.user
    })


# ---------------------------------------------------------------------------
# Watch View
# ---------------------------------------------------------------------------
@login_required
def watch(request):
    featured_stream = StreamSettings.objects.filter(is_featured=True, is_active=True).first()
    active_streams = StreamSettings.objects.filter(is_active=True)

    selected_stream = request.session.get('selected_stream')
    if selected_stream:
        stream = StreamSettings.objects.filter(channel_slug=selected_stream, is_active=True).first()
        if not stream:
            stream = featured_stream
    else:
        stream = featured_stream

    streams_dict = {}
    for s in active_streams:
        key = f"{s.platform}/{s.channel_slug}"
        streams_dict[key] = {
            'platform': s.platform,
            'channel_slug': s.channel_slug,
            'embed_url': s.get_embed_url(),
            'is_featured': s.is_featured,
            'display': str(s),
        }

    context = {
        'stream_title': stream.channel_slug if stream else 'No Stream Available',
        'channel_slug': stream.channel_slug if stream else None,
        'embed_url': stream.get_embed_url() if stream else None,
        'active_streams': active_streams,
        'current_stream': stream,
        'streams_json': json.dumps(streams_dict, cls=DjangoJSONEncoder),
        'CHAT_MESSAGE_MAX_LENGTH': settings.CHAT_MESSAGE_MAX_LENGTH,
    }

    if request.GET.get('popout_chat'):
        context['stream_id'] = request.GET.get('stream_id', 'general')
        return render(request, 'home/chat_popout.html', context)

    return render(request, 'home/watch.html', context)


# ---------------------------------------------------------------------------
# Emote manifest (JSON) — consumed by the chat client for autocomplete + picker
# ---------------------------------------------------------------------------
@login_required
def emote_manifest(request):
    return JsonResponse({'emotes': Emote.get_manifest()})


# ---------------------------------------------------------------------------
# Switch Stream (AJAX)
# ---------------------------------------------------------------------------
def switch_stream(request):
    if request.method == 'POST' and request.user.is_authenticated:
        stream_slug = request.POST.get('stream_slug')
        if stream_slug:
            stream = StreamSettings.objects.filter(channel_slug=stream_slug, is_active=True).first()
            if stream:
                request.session['selected_stream'] = stream_slug
                return JsonResponse({
                    'success': True,
                    'channel_slug': stream_slug,
                    'embed_url': stream.get_embed_url()
                })
    return JsonResponse({'success': False, 'error': 'Invalid request'})
