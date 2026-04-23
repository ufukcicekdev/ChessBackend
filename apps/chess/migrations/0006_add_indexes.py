from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chess", "0005_game_ratings_updated"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="room",
            index=models.Index(fields=["status"], name="room_status_idx"),
        ),
        migrations.AddIndex(
            model_name="game",
            index=models.Index(fields=["result"], name="game_result_idx"),
        ),
        migrations.AddIndex(
            model_name="game",
            index=models.Index(fields=["ended_at"], name="game_ended_at_idx"),
        ),
        migrations.AddIndex(
            model_name="game",
            index=models.Index(fields=["result", "ended_at"], name="game_result_ended_idx"),
        ),
        migrations.AddIndex(
            model_name="move",
            index=models.Index(fields=["timestamp"], name="move_timestamp_idx"),
        ),
    ]
