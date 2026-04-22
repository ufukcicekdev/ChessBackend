import uuid
import math
from django.db import models
from django.conf import settings


class Tournament(models.Model):
    STATUS_REGISTRATION = "registration"
    STATUS_ACTIVE = "active"
    STATUS_FINISHED = "finished"

    STATUS_CHOICES = [
        (STATUS_REGISTRATION, "Registration"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_FINISHED, "Finished"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    max_players = models.IntegerField(default=8)
    time_control = models.IntegerField(default=300)
    increment = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REGISTRATION)
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

    def generate_bracket(self):
        """Generate single-elimination bracket rounds after registration closes."""
        players = list(self.participants.filter(is_active=True).select_related("user"))
        n = len(players)
        if n < 2:
            return

        # Pad to next power of 2 with byes
        next_pow2 = 2 ** math.ceil(math.log2(n))
        total_rounds = int(math.log2(next_pow2))

        round_obj, _ = TournamentRound.objects.get_or_create(
            tournament=self, round_number=1
        )

        for i in range(0, next_pow2, 2):
            player1 = players[i] if i < n else None
            player2 = players[i + 1] if (i + 1) < n else None
            TournamentMatch.objects.get_or_create(
                round=round_obj,
                match_number=i // 2 + 1,
                defaults={"player1": player1, "player2": player2},
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
