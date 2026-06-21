from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count
from django.utils.html import format_html
from .models import (
    CustomUser, StreamSettings, ChatMessage, Emote, Invitation,
    PasswordResetToken, UserTimeout, UserBan, Poll, PollOption, PollVote,
    TrackedChannel, ForumCategory, ForumThread, ForumPost, Announcement,
)


@admin.register(TrackedChannel)
class TrackedChannelAdmin(admin.ModelAdmin):
    list_display = ('name', 'youtube_channel_id', 'is_active')
    list_editable = ('is_active',)
    search_fields = ('name', 'youtube_channel_id')


@admin.register(ForumCategory)
class ForumCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order')
    list_editable = ('order',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ForumThread)
class ForumThreadAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'author', 'is_pinned', 'is_locked', 'last_activity')
    list_editable = ('is_pinned', 'is_locked')
    list_filter = ('category', 'is_pinned', 'is_locked')
    search_fields = ('title',)


@admin.register(ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display = ('thread', 'author', 'created_at')
    search_fields = ('content',)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'is_published', 'created_at')
    list_editable = ('is_published',)
    search_fields = ('title', 'body')


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'display_name', 'email', 'role', 'invites_remaining', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'display_name', 'email')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('display_name', 'first_name', 'last_name', 'email')}),
        ('Invitations', {'fields': ('invites_remaining',)}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'display_name', 'password1', 'password2'),
        }),
    )


@admin.register(StreamSettings)
class StreamSettingsAdmin(admin.ModelAdmin):
    list_display = ('channel_slug', 'platform', 'is_featured', 'is_active', 'updated_at', 'updated_by')
    list_filter = ('platform', 'is_featured', 'is_active')
    search_fields = ('channel_slug', 'youtube_channel_id', 'embed_id')
    ordering = ('-is_featured', '-is_active', '-updated_at')

    fieldsets = (
        ('Stream Information', {
            'fields': ('channel_slug', 'platform', 'youtube_channel_id'),
            'description': 'For YouTube streams, enter either the channel @handle (e.g., @destiny) or the channel ID. For other platforms, use the channel name/slug.'
        }),
        ('Stream Status', {
            'fields': ('is_featured', 'is_active'),
            'description': 'Featured stream will be shown by default. Active streams will be available for selection.'
        }),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'invited_by', 'created_at', 'expires_at', 'used', 'used_at')
    list_filter = ('used',)
    search_fields = ('email', 'invited_by__username')
    readonly_fields = ('token_hash', 'invited_by', 'created_at', 'expires_at', 'used', 'used_at', 'email')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False  # Invitations should be created via the invite flow, not admin

    def has_change_permission(self, request, obj=None):
        return False  # Read-only


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'used')
    list_filter = ('used',)
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('token_hash', 'user', 'created_at', 'expires_at', 'used')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'short_message', 'stream_id', 'timestamp')
    list_filter = ('stream_id',)
    readonly_fields = ('user', 'message', 'stream_id', 'timestamp')
    search_fields = ('user__username', 'message')
    ordering = ('-timestamp',)

    def short_message(self, obj):
        return obj.message[:80] + '...' if len(obj.message) > 80 else obj.message
    short_message.short_description = 'Message'


@admin.register(Emote)
class EmoteAdmin(admin.ModelAdmin):
    list_display = ('preview', 'code', 'is_animated')
    search_fields = ('code',)
    readonly_fields = ('preview',)

    @admin.display(description='Preview')
    def preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" alt="{}" style="height:28px;vertical-align:middle;" />',
                obj.image.url, obj.code,
            )
        return '—'


@admin.register(UserTimeout)
class UserTimeoutAdmin(admin.ModelAdmin):
    list_display = ('user', 'stream_id', 'timed_out_by', 'created_at', 'expires_at')
    list_filter = ('stream_id',)
    search_fields = ('user__username', 'timed_out_by__username')
    readonly_fields = ('user', 'stream_id', 'timed_out_by', 'reason', 'created_at', 'expires_at')
    ordering = ('-created_at',)


@admin.register(UserBan)
class UserBanAdmin(admin.ModelAdmin):
    list_display = ('user', 'banned_by', 'is_permanent', 'created_at', 'expires_at')
    list_filter = ('is_permanent',)
    search_fields = ('user__username', 'banned_by__username')
    readonly_fields = ('user', 'banned_by', 'reason', 'created_at', 'expires_at', 'is_permanent')
    ordering = ('-created_at',)


class PollOptionInline(admin.TabularInline):
    model = PollOption
    extra = 0
    readonly_fields = ('text', 'order', 'vote_count')

    def vote_count(self, obj):
        return obj.votes.count()
    vote_count.short_description = 'Votes'


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ('question', 'stream_id', 'created_by', 'is_active', 'total_votes', 'leading_option', 'created_at', 'expires_at')
    list_filter = ('is_active', 'stream_id')
    search_fields = ('question', 'created_by__username')
    readonly_fields = ('stream_id', 'question', 'created_by', 'created_at', 'expires_at', 'total_votes', 'leading_option')
    ordering = ('-created_at',)
    inlines = [PollOptionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_total_votes=Count('votes'))

    def total_votes(self, obj):
        return obj._total_votes
    total_votes.short_description = 'Total Votes'
    total_votes.admin_order_field = '_total_votes'

    def leading_option(self, obj):
        top = obj.options.annotate(vc=Count('votes')).order_by('-vc').first()
        if top and top.vc > 0:
            return f'{top.text} ({top.vc})'
        return '—'
    leading_option.short_description = 'Leading Option'


# Customize admin site branding
admin.site.site_header = 'Ibokki Administration'
admin.site.site_title = 'Ibokki Admin'
admin.site.index_title = 'Site Management'
