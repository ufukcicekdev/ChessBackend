import secrets

from django.db import migrations, models


_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _gen(length=8):
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def populate_invite_codes(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    used = set(
        Tournament.objects.exclude(invite_code="").values_list("invite_code", flat=True)
    )
    for t in Tournament.objects.filter(invite_code=""):
        code = _gen()
        while code in used:
            code = _gen()
        used.add(code)
        t.invite_code = code
        t.save(update_fields=["invite_code"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tournaments", "0004_add_cancelled_status"),
    ]

    operations = [
        # 1. Add invite_code non-unique first so existing rows can be backfilled.
        migrations.AddField(
            model_name="tournament",
            name="invite_code",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
        migrations.AddField(
            model_name="tournament",
            name="is_private",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tournament",
            name="registration_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tournament",
            name="registration_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="tournament",
            name="status",
            field=models.CharField(
                choices=[
                    ("scheduled", "Scheduled"),
                    ("registration", "Registration"),
                    ("active", "Active"),
                    ("finished", "Finished"),
                    ("cancelled", "Cancelled"),
                ],
                default="registration",
                max_length=20,
            ),
        ),
        # 2. Backfill unique codes for existing tournaments.
        migrations.RunPython(populate_invite_codes, noop),
        # 3. Enforce uniqueness.
        migrations.AlterField(
            model_name="tournament",
            name="invite_code",
            field=models.CharField(blank=True, max_length=12, unique=True),
        ),
    ]
