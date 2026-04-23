from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.chess.models import Challenge


class Command(BaseCommand):
    help = "Expire pending challenges older than 5 minutes"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(seconds=300)
        updated = Challenge.objects.filter(
            status=Challenge.STATUS_PENDING,
            created_at__lt=cutoff,
        ).update(status=Challenge.STATUS_EXPIRED)
        self.stdout.write(f"Expired {updated} challenge(s).")
