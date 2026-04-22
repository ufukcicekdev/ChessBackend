from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from apps.chess.models import Game, Room


class Command(BaseCommand):
    help = "Cancel currently-live chess games (marks rooms abandoned + games aborted)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing to the database.",
        )
        parser.add_argument(
            "--minutes",
            type=int,
            default=None,
            help="If set, only cancel games whose last move (or game start) is older than N minutes.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        minutes = options["minutes"]

        base_qs = (
            Room.objects.select_related("game")
            .filter(status=Room.STATUS_ACTIVE, game__isnull=False)
            .filter(game__result=Game.RESULT_ONGOING)
        )

        if minutes is not None:
            cutoff = timezone.now() - timedelta(minutes=int(minutes))
            rooms = []
            for room in base_qs.iterator(chunk_size=200):
                game = room.game
                ts = game.last_move_at or game.started_at or game.created_at
                if ts and ts <= cutoff:
                    rooms.append(room)
        else:
            rooms = list(base_qs)
        self.stdout.write(f"Found {len(rooms)} live ongoing game(s) to cancel.")

        if dry_run:
            for room in rooms[:50]:
                self.stdout.write(f"- would cancel room={room.id} game={room.game_id}")
            if len(rooms) > 50:
                self.stdout.write(f"... and {len(rooms) - 50} more")
            return

        now = timezone.now()
        with transaction.atomic():
            for room in rooms:
                game = room.game
                room.status = Room.STATUS_ABANDONED
                room.save(update_fields=["status"])

                game.result = Game.RESULT_ABORTED
                game.ended_at = now
                game.save(update_fields=["result", "ended_at"])

        self.stdout.write(self.style.SUCCESS(f"Cancelled {len(rooms)} game(s)."))
