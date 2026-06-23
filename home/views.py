# home/views.py

import time
from django.shortcuts import redirect, render, get_object_or_404
from django.conf import settings
from django.contrib.auth import login, authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import (
    StreamSettings, Invitation, PasswordResetToken, Emote, EmoteFavorite,
    TrackedChannel, ForumCategory, ForumThread, ForumPost, Announcement,
    Podcast, Subscription, EmailVerificationToken,
    SubscriptionProduct, Coupon, Transaction,
    BILLING_MONTHLY, BILLING_ANNUAL, _money,
)
from .youtube import get_latest_videos
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q, F
from django.db import transaction as db_transaction
from datetime import timedelta


def _is_admin(user):
    """Admins = role 'admin', Django staff, or superuser."""
    return user.is_authenticated and (
        getattr(user, 'role', None) == 'admin' or user.is_staff or user.is_superuser
    )


def _category_access_q(user, field='required_podcast'):
    """Q over a Podcast FK (`field`) selecting rows the user may access:
    ungated rows, plus rows whose podcast the user actively subscribes to.
    Site admins get everything."""
    if user.is_site_admin:
        return Q()
    ids = list(user.active_subscriptions().values_list('podcast_id', flat=True))
    return Q(**{f'{field}__isnull': True}) | Q(**{f'{field}__id__in': ids})
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
            # If the credentials are correct but the account is unverified,
            # nudge the user to verify rather than showing "invalid".
            pending = User.objects.filter(username=username, is_active=False).first()
            if pending and pending.check_password(password):
                messages.error(request, 'Please verify your email before logging in -- check your inbox for the verification link.')
            else:
                messages.error(request, 'Invalid username or password.')

    return render(request, 'home/login.html')


# ---------------------------------------------------------------------------
# Registration View (invite-based)
# ---------------------------------------------------------------------------
def _send_verification_email(user):
    """Email a one-time verification link to a freshly-registered (inactive) user."""
    _, raw_token = EmailVerificationToken.create_token(user)
    verify_url = f"{settings.BASE_URL}/verify-email/{raw_token}/"
    body = render_to_string('home/email/verify_email.txt', {
        'username': user.display_name or user.username,
        'verify_url': verify_url,
        'expiry_hours': 48,
    })
    try:
        send_mail('Verify your Ibokki account', body, settings.DEFAULT_FROM_EMAIL,
                  [user.email], fail_silently=False)
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {e}")


def register_view(request):
    """Open registration. Creates an inactive account and emails a verification link.

    Access to the site is now open; gated podcast areas require a subscription.
    """
    if request.user.is_authenticated:
        return redirect('landing')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        errors = []
        if not username:
            errors.append('Username is required.')
        elif User.objects.filter(username=username).exists():
            errors.append('That username is already taken.')
        if not email:
            errors.append('Email is required.')
        elif User.objects.filter(email=email).exists():
            errors.append('An account with that email already exists.')
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
            return render(request, 'home/register.html', {'username': username, 'email': email})

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_active = False  # stays inactive until the email is verified
        user.save()
        _send_verification_email(user)
        messages.success(request, 'Account created! Check your email for a link to verify and activate your account.')
        return redirect('login')

    return render(request, 'home/register.html')


def verify_email_view(request, token):
    """Activate an account from the emailed verification link."""
    token_obj = EmailVerificationToken.validate_token(token)
    if not token_obj:
        return render(request, 'home/verify_email.html', {'invalid': True})
    user = token_obj.user
    user.is_active = True
    user.save(update_fields=['is_active'])
    token_obj.used = True
    token_obj.save(update_fields=['used'])
    messages.success(request, 'Email verified! You can now log in.')
    return redirect('login')


def register_invite_view(request, token):
    """Registration page -- accessed via an invitation link (still supported)."""
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

    latest_posts = (
        ForumPost.objects
        .select_related('thread', 'thread__category', 'author')
        .filter(_category_access_q(request.user, 'thread__category__required_podcast'))
        .order_by('-created_at')[:6]
    )

    context = {
        "current_stream_title": title,
        'user': request.user,
        'latest_videos': get_latest_videos(limit=5),
        'latest_posts': latest_posts,
        'latest_announcement': Announcement.objects.filter(is_published=True).first(),
    }
    return render(request, 'home/landing.html', context)


@login_required
def all_videos(request):
    """Full listing of the latest videos across all tracked channels."""
    return render(request, 'home/videos.html', {
        'videos': get_latest_videos(limit=None),
    })


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
@ensure_csrf_cookie
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
    favorites = list(
        EmoteFavorite.objects.filter(user=request.user).values_list('emote__code', flat=True)
    )
    return JsonResponse({'emotes': Emote.get_manifest(), 'favorites': favorites})


@login_required
@require_POST
def toggle_emote_favorite(request):
    code = request.POST.get('code', '')
    favorited = request.POST.get('favorited') == 'true'
    emote = Emote.objects.filter(code=code).first()
    if not emote:
        return JsonResponse({'ok': False, 'error': 'Unknown emote'}, status=404)
    if favorited:
        EmoteFavorite.objects.get_or_create(user=request.user, emote=emote)
    else:
        EmoteFavorite.objects.filter(user=request.user, emote=emote).delete()
    return JsonResponse({'ok': True, 'favorited': favorited})


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


# ---------------------------------------------------------------------------
# Forum (minimal)
# ---------------------------------------------------------------------------
@login_required
def forum_index(request):
    categories = list(ForumCategory.objects.select_related('required_podcast').all())
    # Mark which sections the user can enter (locked ones still show, as a teaser).
    for c in categories:
        c.accessible = request.user.has_podcast_access(c.required_podcast)
    recent_threads = (
        ForumThread.objects.select_related('category', 'author')
        .filter(_category_access_q(request.user, 'category__required_podcast'))
        .order_by('-last_activity')[:15]
    )
    return render(request, 'home/forum/index.html', {
        'categories': categories,
        'recent_threads': recent_threads,
    })


@login_required
def forum_category(request, slug):
    category = get_object_or_404(ForumCategory, slug=slug)
    if not request.user.has_podcast_access(category.required_podcast):
        messages.error(request, f'That section requires a {category.required_podcast.name} subscription.')
        return redirect('forum_index')
    threads = category.threads.select_related('author').all()
    return render(request, 'home/forum/category.html', {
        'category': category,
        'threads': threads,
    })


@login_required
def forum_thread(request, pk):
    thread = get_object_or_404(
        ForumThread.objects.select_related('category', 'author', 'category__required_podcast'), pk=pk
    )
    if not request.user.has_podcast_access(thread.category.required_podcast):
        messages.error(request, f'That section requires a {thread.category.required_podcast.name} subscription.')
        return redirect('forum_index')
    posts = thread.posts.select_related('author').all()
    return render(request, 'home/forum/thread.html', {
        'thread': thread,
        'posts': posts,
    })


@login_required
def forum_new_thread(request, slug):
    category = get_object_or_404(ForumCategory, slug=slug)
    if not request.user.has_podcast_access(category.required_podcast):
        messages.error(request, f'That section requires a {category.required_podcast.name} subscription.')
        return redirect('forum_index')
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        content = (request.POST.get('content') or '').strip()
        if not title or not content:
            messages.error(request, 'A title and a message are required.')
        else:
            thread = ForumThread.objects.create(
                category=category, title=title[:200], author=request.user,
                last_activity=timezone.now(),
            )
            ForumPost.objects.create(thread=thread, author=request.user, content=content)
            return redirect('forum_thread', pk=thread.pk)
    return render(request, 'home/forum/new_thread.html', {'category': category})


@login_required
@require_POST
def forum_reply(request, pk):
    thread = get_object_or_404(ForumThread.objects.select_related('category', 'category__required_podcast'), pk=pk)
    if not request.user.has_podcast_access(thread.category.required_podcast):
        messages.error(request, 'You do not have access to that section.')
        return redirect('forum_index')
    if thread.is_locked and not _is_admin(request.user):
        messages.error(request, 'This thread is locked.')
        return redirect('forum_thread', pk=thread.pk)
    content = (request.POST.get('content') or '').strip()
    if content:
        ForumPost.objects.create(thread=thread, author=request.user, content=content)
        thread.last_activity = timezone.now()
        thread.save(update_fields=['last_activity'])
    else:
        messages.error(request, 'Reply cannot be empty.')
    return redirect('forum_thread', pk=thread.pk)


# ---------------------------------------------------------------------------
# Announcements (public list/detail + admin management)
# ---------------------------------------------------------------------------
@login_required
def announcement_list(request):
    announcements = Announcement.objects.filter(is_published=True)
    return render(request, 'home/announcements/list.html', {
        'announcements': announcements,
    })


@login_required
def announcement_detail(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if not announcement.is_published and not _is_admin(request.user):
        return redirect('announcement_list')
    return render(request, 'home/announcements/detail.html', {
        'announcement': announcement,
    })


@login_required
def announcement_admin(request):
    if not _is_admin(request.user):
        return redirect('landing')
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        body = (request.POST.get('body') or '').strip()
        is_published = request.POST.get('is_published') == 'on'
        if not title:
            messages.error(request, 'Title is required.')
        else:
            Announcement.objects.create(
                title=title[:200], body=body, author=request.user,
                is_published=is_published,
                banner_image=request.FILES.get('banner_image'),
            )
            messages.success(request, 'Announcement created.')
            return redirect('announcement_admin')
    return render(request, 'home/announcements/admin.html', {
        'announcements': Announcement.objects.all(),
    })


@login_required
def announcement_edit(request, pk):
    if not _is_admin(request.user):
        return redirect('landing')
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        announcement.title = (request.POST.get('title') or announcement.title).strip()[:200]
        announcement.body = (request.POST.get('body') or '').strip()
        announcement.is_published = request.POST.get('is_published') == 'on'
        if request.FILES.get('banner_image'):
            announcement.banner_image = request.FILES['banner_image']
        announcement.save()
        messages.success(request, 'Announcement updated.')
        return redirect('announcement_admin')
    return render(request, 'home/announcements/edit.html', {'announcement': announcement})


@login_required
@require_POST
def announcement_delete(request, pk):
    if not _is_admin(request.user):
        return redirect('landing')
    get_object_or_404(Announcement, pk=pk).delete()
    messages.success(request, 'Announcement deleted.')
    return redirect('announcement_admin')


# --- Subscription checkout ---------------------------------------------------

def _interval_label(interval):
    return 'year' if interval == BILLING_ANNUAL else 'month'


def _price_quote(product, interval, code):
    """Compute a checkout quote. Returns a dict with base/discount/final and an
    optional coupon error message for invalid codes."""
    base = product.price_for(interval)
    coupon = None
    discount = 0
    error = ''
    code = (code or '').strip()
    if code:
        coupon = Coupon.find(code)
        if coupon is None:
            error = 'That code is not valid.'
        elif not coupon.is_redeemable_now():
            error = 'That code has expired or is no longer available.'
            coupon = None
        elif not coupon.applies_to(product):
            error = 'That code does not apply to this product.'
            coupon = None
        else:
            discount = coupon.percent_off
    final = _money(base * (100 - discount) / 100)
    return {
        'product': product,
        'interval': interval,
        'interval_label': _interval_label(interval),
        'base': base,
        'coupon': coupon,
        'code': code,
        'discount': discount,
        'discount_amount': _money(base - final),
        'final': final,
        'is_free': final <= 0,
        'error': error,
    }


@login_required
def subscribe_index(request):
    products = SubscriptionProduct.objects.filter(is_active=True).select_related('podcast')
    owned = set(request.user.active_subscriptions().values_list('podcast_id', flat=True))
    for p in products:
        p.already_active = p.podcast_id in owned
    return render(request, 'home/subscribe/index.html', {'products': products})


@login_required
def checkout(request, product_id):
    product = get_object_or_404(SubscriptionProduct, pk=product_id, is_active=True)
    interval = request.POST.get('interval') or request.GET.get('interval') or BILLING_MONTHLY
    if interval not in (BILLING_MONTHLY, BILLING_ANNUAL):
        interval = BILLING_MONTHLY
    code = request.POST.get('coupon_code', '')
    action = request.POST.get('action', '')

    quote = _price_quote(product, interval, code)

    if request.method == 'POST' and action == 'complete':
        if not quote['is_free']:
            messages.error(
                request,
                'Online payment is not available yet. A coupon covering the full '
                'price is required to complete checkout.',
            )
        else:
            txn = _complete_checkout(request.user, quote)
            return redirect('checkout_success', pk=txn.pk)

    if quote['error']:
        messages.error(request, quote['error'])

    return render(request, 'home/subscribe/checkout.html', {'q': quote})


def _complete_checkout(user, quote):
    """Record a completed (free) transaction and grant/extend the subscription."""
    product = quote['product']
    interval = quote['interval']
    now = timezone.now()
    span = timedelta(days=365) if interval == BILLING_ANNUAL else timedelta(days=30)

    with db_transaction.atomic():
        coupon = quote['coupon']
        if coupon is not None:
            Coupon.objects.filter(pk=coupon.pk).update(times_used=F('times_used') + 1)

        existing = Subscription.objects.filter(user=user, podcast=product.podcast).first()
        anchor = now
        if existing and existing.expires_at and existing.expires_at > now:
            anchor = existing.expires_at
        new_expiry = anchor + span

        Subscription.objects.update_or_create(
            user=user, podcast=product.podcast,
            defaults={'is_active': True, 'expires_at': new_expiry},
        )

        txn = Transaction.objects.create(
            user=user,
            product=product,
            product_name=product.name,
            billing_interval=interval,
            base_price=quote['base'],
            coupon=coupon,
            coupon_code=quote['code'],
            discount_percent=quote['discount'],
            final_price=quote['final'],
            status=Transaction.STATUS_COMPLETED,
            granted_until=new_expiry,
            completed_at=now,
        )
    return txn


@login_required
def checkout_success(request, pk):
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    return render(request, 'home/subscribe/success.html', {'txn': txn})
