from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, StreamSettings, ChatMessage, Emote, Invitation, PasswordResetToken


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'display_name', 'email', 'invites_remaining', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'display_name', 'email')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('display_name', 'first_name', 'last_name', 'email')}),
        ('Invitations', {'fields': ('invites_remaining',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
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
    search_fields = ('channel_slug', 'youtube_channel_id')
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
    list_display = ('code', 'is_animated')
    search_fields = ('code',)


# Customize admin site branding
admin.site.site_header = 'Ibokki Administration'
admin.site.site_title = 'Ibokki Admin'
admin.site.index_title = 'Site Management'
