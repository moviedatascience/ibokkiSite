# Generated manually for invite-only auth overhaul

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def deduplicate_emails(apps, schema_editor):
    """
    Ensure all user emails are unique before adding the unique constraint.
    Duplicate or blank emails get a placeholder based on username.
    """
    CustomUser = apps.get_model("home", "CustomUser")
    seen_emails = set()
    for user in CustomUser.objects.all().order_by("date_joined"):
        email = (user.email or "").strip().lower()
        if not email or email in seen_emails:
            # Assign a placeholder unique email
            user.email = f"{user.username.replace('#', '_')}@placeholder.ibokki.com"
            user.save(update_fields=["email"])
        seen_emails.add(user.email.strip().lower())


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0003_chatmessage_stream_id_and_more"),
    ]

    operations = [
        # --- CustomUser changes ---
        # Add invites_remaining field
        migrations.AddField(
            model_name="customuser",
            name="invites_remaining",
            field=models.PositiveIntegerField(default=2),
        ),

        # Fix duplicate emails before adding unique constraint
        migrations.RunPython(deduplicate_emails, migrations.RunPython.noop),

        # Make email unique
        migrations.AlterField(
            model_name="customuser",
            name="email",
            field=models.EmailField(max_length=254, unique=True),
        ),

        # --- StreamSettings: ensure updated_by has blank=True ---
        migrations.AlterField(
            model_name="streamsettings",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # --- Invitation model ---
        migrations.CreateModel(
            name="Invitation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("email", models.EmailField(max_length=254)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("used", models.BooleanField(default=False)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "invited_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invitations_sent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["token_hash"],
                        name="home_invita_token_h_idx",
                    ),
                    models.Index(
                        fields=["email"],
                        name="home_invita_email_idx",
                    ),
                ],
            },
        ),

        # --- PasswordResetToken model ---
        migrations.CreateModel(
            name="PasswordResetToken",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("used", models.BooleanField(default=False)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="password_reset_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["token_hash"],
                        name="home_passwo_token_h_idx",
                    ),
                ],
            },
        ),
    ]
