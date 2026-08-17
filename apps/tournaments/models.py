import uuid
import math
import secrets
import string
from django.db import models
from django.conf import settings


def generate_invite_code(length: int = 8) -> str:
    """Short, unambiguous, uppercase invite code (no 0/O/1/I)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _seed_positions(size: int) -> list[int]:
    """Standard single-elimination seed order for a power-of-two bracket.

    e.g. size 4 -> [1, 4, 2, 3];  size 8 -> [1, 8, 4, 5, 2, 7, 3, 6].
    Each adjacent pair (index 2k, 2k+1) has the lower seed first.
    """
    order = [1, 2]
    while len(order) < size:
        length = len(order) * 2
        expanded: list[int] = []
        for x in order:
            expanded.append(x)
            expanded.append(length + 1 - x)
        order = expanded
    return order


class Tournament(models.Model):
    STATUS_SCHEDULED = "scheduled"
    STATUS_REGISTRATION = "registration"
    STATUS_ACTIVE = "active"
    STATUS_FINISHED = "finished"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_REGISTRATION, "Registration"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_FINISHED, "Finished"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    max_players = models.IntegerField(default=8)
    time_control = models.IntegerField(default=300)
    increment = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REGISTRATION)

    # Invite / visibility
    invite_code = models.CharField(max_length=12, unique=True, blank=True)
    is_private = models.BooleanField(default=False)

    # Registration window. If null, registration is open until the creator starts it manually.
    registration_start = models.DateTimeField(null=True, blank=True)
    registration_end = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="created_tournaments"
    )
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="won_tournaments"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} [{self.status}]"

    def save(self, *args, **kwargs):
        if not self.invite_code:
            code = generate_invite_code()
            while Tournament.objects.filter(invite_code=code).exists():
                code = generate_invite_code()
            self.invite_code = code
        super().save(*args, **kwargs)

    def generate_bracket(self):
        """Generate the seeded single-elimination first round after registration closes.

        Players are seeded by rating (highest = seed 1). The bracket is padded to
        the next power of two with byes, placed opposite the top seeds so the
        strongest players get the byes and don't meet each other early.
        """
        players = list(self.participants.filter(is_active=True).select_related("user"))
        n = len(players)
        if n < 2:
            return

        # Seed by rating (highest first) and persist the seed number.
        players.sort(key=lambda p: (p.user.rating if p.user else 0), reverse=True)
        for idx, p in enumerate(players, start=1):
            if p.seed != idx:
                p.seed = idx
                p.save(update_fields=["seed"])

        next_pow2 = 2 ** math.ceil(math.log2(n))
        positions = _seed_positions(next_pow2)          # seed number per bracket slot
        seed_map = {i + 1: players[i] for i in range(n)}  # seed -> participant (missing = bye)
        slots = [seed_map.get(s) for s in positions]

        round_obj, _ = TournamentRound.objects.get_or_create(
            tournament=self, round_number=1
        )

        # positions guarantees the better (lower) seed is first in each pair,
        # so any bye (None) always lands in player2 → handled by Match.save().
        for i in range(0, next_pow2, 2):
            TournamentMatch.objects.get_or_create(
                round=round_obj,
                match_number=i // 2 + 1,
                defaults={"player1": slots[i], "player2": slots[i + 1]},
            )


class TournamentParticipant(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    seed = models.IntegerField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("tournament", "user")]

    def __str__(self):
        return f"{self.user.username} in {self.tournament.name}"


class TournamentRound(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="rounds")
    round_number = models.IntegerField()

    class Meta:
        unique_together = [("tournament", "round_number")]
        ordering = ["round_number"]

    def __str__(self):
        return f"{self.tournament.name} - Round {self.round_number}"


class TournamentMatch(models.Model):
    round = models.ForeignKey(TournamentRound, on_delete=models.CASCADE, related_name="matches")
    match_number = models.IntegerField()
    player1 = models.ForeignKey(
        TournamentParticipant, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="matches_as_player1"
    )
    player2 = models.ForeignKey(
        TournamentParticipant, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="matches_as_player2"
    )
    winner = models.ForeignKey(
        TournamentParticipant, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="won_matches"
    )
    is_bye = models.BooleanField(default=False)
    room = models.OneToOneField(
        "chess.Room", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="tournament_match"
    )

    class Meta:
        unique_together = [("round", "match_number")]
        ordering = ["match_number"]

    def save(self, *args, **kwargs):
        if self.player1 and not self.player2:
            self.is_bye = True
            self.winner = self.player1
        super().save(*args, **kwargs)

    def __str__(self):
        p1 = self.player1.user.username if self.player1 else "BYE"
        p2 = self.player2.user.username if self.player2 else "BYE"
        return f"R{self.round.round_number} M{self.match_number}: {p1} vs {p2}"
