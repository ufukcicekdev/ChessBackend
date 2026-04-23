from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chess", "0005_game_ratings_updated"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS room_status_idx ON chess_room (status);
                CREATE INDEX IF NOT EXISTS game_result_idx ON chess_game (result);
                CREATE INDEX IF NOT EXISTS game_ended_at_idx ON chess_game (ended_at);
                CREATE INDEX IF NOT EXISTS game_result_ended_idx ON chess_game (result, ended_at);
                CREATE INDEX IF NOT EXISTS move_timestamp_idx ON chess_move (timestamp);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS room_status_idx;
                DROP INDEX IF EXISTS game_result_idx;
                DROP INDEX IF EXISTS game_ended_at_idx;
                DROP INDEX IF EXISTS game_result_ended_idx;
                DROP INDEX IF EXISTS move_timestamp_idx;
            """,
        ),
    ]
