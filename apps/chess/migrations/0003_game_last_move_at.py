from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chess", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="last_move_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
