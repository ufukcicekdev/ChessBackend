import random
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

import redis

from .models import Room, Game


@dataclass(frozen=True)
class MatchmakingResult:
    status: str  # "matched" | "queued"
    room_id: str | None = None


def _redis_client() -> redis.Redis:
    if not getattr(settings, "REDIS_URL", None):
        raise RuntimeError("REDIS_URL is not configured")
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _queue_key(time_control: int, increment: int) -> str:
    return f"mm:q:{time_control}:{increment}"


def _queued_set_key(time_control: int, increment: int) -> str:
    return f"mm:queued:{time_control}:{increment}"


def _match_key(user_id: int) -> str:
    return f"mm:match:{user_id}"


def _lock_key(time_control: int, increment: int) -> str:
    return f"mm:lock:{time_control}:{increment}"


def join_queue(*, user, time_control: int, increment: int) -> MatchmakingResult:
    """
    Redis-backed matchmaking:
    - If another user is waiting in the same queue (time_control + increment), create a room and match.
    - Otherwise enqueue the user and return queued status.
    """
    r = _redis_client()
    lock = _lock_key(time_control, increment)
    queue = _queue_key(time_control, increment)
    queued_set = _queued_set_key(time_control, increment)

    # Quick path: if we were already matched by someone else.
    existing_room = r.get(_match_key(user.id))
    if existing_room:
        r.delete(_match_key(user.id))
        return MatchmakingResult(status="matched", room_id=existing_room)

    # Coarse queue lock to prevent race conditions.
    lock_token = str(random.random())
    if not r.set(lock, lock_token, nx=True, px=3000):
        # If another join is in progress, try again quickly.
        existing_room = r.get(_match_key(user.id))
        if existing_room:
            r.delete(_match_key(user.id))
            return MatchmakingResult(status="matched", room_id=existing_room)
        return MatchmakingResult(status="queued", room_id=None)

    try:
        # Avoid duplicates
        r.sadd(queued_set, str(user.id))
        r.expire(queued_set, 600)

        opponent_id: str | None = None
        for _ in range(10):  # bounded cleanup
            candidate = r.lpop(queue)
            if not candidate:
                break
            if candidate == str(user.id):
                continue
            # ensure candidate is still queued
            if r.srem(queued_set, candidate):
                opponent_id = candidate
                break

        if not opponent_id:
            # enqueue and return
            r.rpush(queue, str(user.id))
            r.expire(queue, 600)
            return MatchmakingResult(status="queued", room_id=None)

        # Create a room & game in DB
        from django.contrib.auth import get_user_model

        User = get_user_model()
        opponent = User.objects.get(id=int(opponent_id))

        with transaction.atomic():
            room = Room.objects.create(
                name="Matchmaking game",
                is_public=True,
                time_control=time_control,
                increment=increment,
                status=Room.STATUS_ACTIVE,
                created_by=user,
            )
            # Randomize colors
            if random.choice([True, False]):
                white, black = user, opponent
            else:
                white, black = opponent, user

            Game.objects.create(
                room=room,
                white_player=white,
                black_player=black,
                white_time_remaining=time_control,
                black_time_remaining=time_control,
                started_at=timezone.now(),
            )

        room_id = str(room.id)
        # Notify both players via Redis "match" keys (polled via REST).
        r.setex(_match_key(user.id), 120, room_id)
        r.setex(_match_key(opponent.id), 120, room_id)
        return MatchmakingResult(status="matched", room_id=room_id)
    finally:
        # Best-effort unlock
        r.delete(lock)


def leave_queue(*, user, time_control: int, increment: int) -> None:
    r = _redis_client()
    queue = _queue_key(time_control, increment)
    queued_set = _queued_set_key(time_control, increment)
    r.srem(queued_set, str(user.id))
    # Remove occurrences from list (O(n), but queue is short-lived).
    r.lrem(queue, 0, str(user.id))
    r.delete(_match_key(user.id))


def status(*, user, time_control: int, increment: int) -> MatchmakingResult:
    r = _redis_client()
    room_id = r.get(_match_key(user.id))
    if room_id:
        r.delete(_match_key(user.id))
        return MatchmakingResult(status="matched", room_id=room_id)

    queued_set = _queued_set_key(time_control, increment)
    if r.sismember(queued_set, str(user.id)):
        return MatchmakingResult(status="queued", room_id=None)
    return MatchmakingResult(status="queued", room_id=None)

