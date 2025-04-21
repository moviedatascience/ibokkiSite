from django.db import migrations

def fix_multiple_active_streams(apps, schema_editor):
    StreamSettings = apps.get_model('home', 'StreamSettings')
    # Get all active streams
    active_streams = StreamSettings.objects.filter(is_active=True)
    if active_streams.count() > 1:
        # Keep the most recently updated one active
        latest = active_streams.order_by('-updated_at').first()
        # Deactivate all others
        StreamSettings.objects.exclude(id=latest.id).update(is_active=False)

class Migration(migrations.Migration):
    dependencies = [
        ('home', '0002_streamsettings_is_active'),
    ]

    operations = [
        migrations.RunPython(fix_multiple_active_streams),
    ] 