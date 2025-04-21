from django.contrib import admin
from .models import StreamSettings

@admin.register(StreamSettings)
class StreamSettingsAdmin(admin.ModelAdmin):
    list_display = ('channel_slug', 'is_active', 'updated_by', 'updated_at')
    list_editable = ('is_active',)
    readonly_fields = ('updated_by', 'updated_at')
    list_filter = ('is_active',)

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
