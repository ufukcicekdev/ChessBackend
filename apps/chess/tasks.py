from celery import shared_task


def _get_redis():
    try:
        import redis as redis_lib
        from django.conf import settings
        r = redis_lib.from_url(settings.REDIS_URL or "", decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


@shared_task(bind=True, max_retries=0)
def abandon_game_task(self, room_id: str, color: str):
    """
    Called after ABANDON_GRACE_SECONDS if a player hasn't reconnected.
    Checks the Redis sentinel key first — if it's gone, the player reconnected
    and this task should be a no-op.
    """
    r = _get_redis()
    if r:
        sentinel = f"abandon:{room_id}:{color}"
        if not r.get(sentinel):
            return  # player reconnected; key was deleted on reconnect
        r.delete(sentinel)
        r.delete(f"abandon_task:{room_id}:{color}")

    from django.utils import timezone
    from .models import Game, Room

    try:
        game = Game.objects.select_related(
            "white_player", "black_player", "room"
        ).get(room_id=room_id)
    except Game.DoesNotExist:
        return

    if game.result != Game.RESULT_ONGOING:
        return

    winner = "black" if color == "white" else "white"
    now = timezone.now()
    game.result = winner
    game.ended_at = now
    game.save(update_fields=["result", "ended_at"])
    game.room.status = Room.STATUS_FINISHED
    game.room.save(update_fields=["status"])

    from .utils import update_ratings
    update_ratings(game)

    # Broadcast game_over to the room group via the channel layer
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"chess_{room_id}",
        {"type": "game_over_event", "result": winner, "reason": "abandonment"},
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def update_ratings_task(self, game_id: str):
    """Deferred rating update — runs in Celery worker, not in the WS consumer."""
    from .models import Game
    try:
        game = Game.objects.select_related("white_player", "black_player").get(id=game_id)
    except Game.DoesNotExist:
        return
    from .utils import update_ratings
    update_ratings(game)
