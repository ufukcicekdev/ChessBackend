import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chess", "0006_add_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Challenge",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("time_control", models.IntegerField(default=300)),
                ("increment", models.IntegerField(default=0)),
                ("status", models.CharField(default="pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("challenger", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sent_challenges", to=settings.AUTH_USER_MODEL)),
                ("challenged", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="received_challenges", to=settings.AUTH_USER_MODEL)),
                ("room", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="chess.room")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
