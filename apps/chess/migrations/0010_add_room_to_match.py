"""
Sync Django migration state with indexes that already exist in the DB.
Uses SeparateDatabaseAndState so no DDL is executed — only the ORM state is updated.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chess", "0009_add_rating_change_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # DB already has these indexes — do nothing
            state_operations=[
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
            ],
        ),
    ]
