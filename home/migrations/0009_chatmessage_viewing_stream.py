# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0008_rename_home_invita_token_h_idx_home_invita_token_h_d2de43_idx_and_more"),
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
