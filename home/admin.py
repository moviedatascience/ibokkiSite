from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, StreamSettings

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'display_name', 'email', 'first_name', 'last_name', 'is_staff')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('display_name', 'first_name', 'last_name', 'email')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'display_name', 'password1', 'password2'),
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
