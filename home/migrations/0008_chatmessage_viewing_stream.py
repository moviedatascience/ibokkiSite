# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0007_set_admin_role_for_staff"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatmessage",
            name="viewing_stream",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Stream the user was viewing when they sent this message",
                max_length=100,
            ),
        ),
    ]
