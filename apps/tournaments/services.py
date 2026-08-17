"""Tournament lifecycle & bracket helpers.

Used by both the Celery beat task (production) and lazily from the API views
(so time-based transitions still happen in local dev without a beat worker).
"""
from django.db import transaction
from django.utils import timezone

from .models import Tournament, TournamentMatch, TournamentRound


def transition_tournament(t: Tournament) -> bool:
    """Apply any due time-based state transitions to a single tournament.

    scheduled  -> registration   (when registration_start passes)
    registration -> active        (when registration_end passes, >=2 players)
    registration -> cancelled     (when registration_end passes, <2 players)

    Returns True if the tournament changed.
    """
    now = timezone.now()
    changed = False

    if (
        t.status == Tournament.STATUS_SCHEDULED
        and t.registration_start
        and now >= t.registration_start
    ):
        t.status = Tournament.STATUS_REGISTRATION
        t.save(update_fields=["status"])
        changed = True

    if (
        t.status == Tournament.STATUS_REGISTRATION
        and t.registration_end
        and now >= t.registration_end
    ):
        if t.participants.filter(is_active=True).count() >= 2:
            start_tournament_now(t)
        else:
            t.status = Tournament.STATUS_CANCELLED
            t.save(update_fields=["status"])
        changed = True

    return changed


def start_tournament_now(t: Tournament) -> None:
    """Move a tournament to active, build the seeded bracket and open round-1 rooms."""
    with transaction.atomic():
        t.status = Tournament.STATUS_ACTIVE
        t.started_at = timezone.now()
        t.save(update_fields=["status", "started_at"])
        t.generate_bracket()
    create_rooms_for_current_round(t)


def create_rooms_for_current_round(t: Tournament) -> None:
    """Auto-create a private Room for every playable match in the latest round.

    Mirrors the manual `create_match_room` flow (Room only; colors are assigned
    first-come by the game consumer, restricted to the two matched players).
    """
    from apps.chess.models import Room

    current_round = t.rounds.order_by("-round_number").first()
    if not current_round:
        return

    matches = current_round.matches.select_related("player1__user", "player2__user")
    for match in matches:
        if match.is_bye or match.winner_id or match.room_id:
            continue
        if not (match.player1 and match.player2):
            continue
        room = Room.objects.create(
            name=f"{t.name} · R{current_round.round_number} #{match.match_number}",
            time_control=t.time_control,
            increment=t.increment,
            created_by=match.player1.user,
            is_public=False,
        )
        match.room = room
        match.save(update_fields=["room"])

        # Push-notify both matched players that their game is ready.
        _notify_match_ready(t, current_round.round_number, match, room)


def _notify_match_ready(t, round_number, match, room):
    """Send an FCM push to the two players of a freshly-opened match."""
    try:
        from apps.users.fcm import send_to_users

        user_ids = [match.player1.user_id, match.player2.user_id]
        opponents = {
            match.player1.user_id: match.player2.user.username,
            match.player2.user_id: match.player1.user.username,
        }
        link = f"/room/{room.id}"
        for uid in user_ids:
            send_to_users(
                [uid],
                title=f"{t.name} — your match is ready",
                body=f"Round {round_number}: you're paired against {opponents[uid]}. Tap to play.",
                data={"type": "tournament_match", "tournament_id": str(t.id), "room_id": str(room.id)},
                link=link,
            )
    except Exception:
        # Notifications must never break bracket progression.
        pass


def run_tournament_lifecycle() -> int:
    """Process all tournaments that may need a time-based transition.

    Returns the number of tournaments that changed. Safe to call repeatedly.
    """
    qs = Tournament.objects.filter(
        status__in=[Tournament.STATUS_SCHEDULED, Tournament.STATUS_REGISTRATION]
    ).filter(
        models_q_due()
    )
    changed = 0
    for t in qs:
        try:
            if transition_tournament(t):
                changed += 1
        except Exception:
            # Never let one bad tournament break the whole sweep.
            continue
    return changed


def models_q_due():
    """Q filter: tournaments whose registration_start or registration_end is due."""
    from django.db.models import Q

    now = timezone.now()
    return Q(registration_start__lte=now) | Q(registration_end__lte=now)
