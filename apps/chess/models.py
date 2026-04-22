import uuid
from django.db import models
from django.conf import settings

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class Room(models.Model):
    STATUS_WAITING = "waiting"
    STATUS_ACTIVE = "active"
    STATUS_FINISHED = "finished"
    STATUS_ABANDONED = "abandoned"

    STATUS_CHOICES = [
        (STATUS_WAITING, "Waiting"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_FINISHED, "Finished"),
        (STATUS_ABANDONED, "Abandoned"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True)
    is_public = models.BooleanField(default=True)
    time_control = models.IntegerField(default=600, help_text="Seconds per player")
    increment = models.IntegerField(default=0, help_text="Seconds added per move")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WAITING)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="created_rooms"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    tournament = models.ForeignKey(
        "tournaments.Tournament", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="rooms"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Room {self.id} [{self.status}]"


class Game(models.Model):
    RESULT_WHITE = "white"
    RESULT_BLACK = "black"
    RESULT_DRAW = "draw"
    RESULT_ONGOING = "ongoing"
    RESULT_ABORTED = "aborted"

    RESULT_CHOICES = [
        (RESULT_WHITE, "White wins"),
        (RESULT_BLACK, "Black wins"),
        (RESULT_DRAW, "Draw"),
        (RESULT_ONGOING, "Ongoing"),
        (RESULT_ABORTED, "Aborted"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name="game")
    white_player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="white_games"
    )
    black_player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="black_games"
    )
    fen = models.TextField(default=STARTING_FEN)
    pgn = models.TextField(blank=True)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, default=RESULT_ONGOING)
    white_time_remaining = models.IntegerField(default=600)
    black_time_remaining = models.IntegerField(default=600)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    # Used for server-side clock updates between moves.
    last_move_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        white = self.white_player.username if self.white_player else "?"
        black = self.black_player.username if self.black_player else "?"
        return f"{white} vs {black} [{self.result}]"


class Move(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="moves")
    move_number = models.IntegerField()
    san = models.CharField(max_length=10, help_text="Standard Algebraic Notation, e.g. e4, Nf3")
    uci = models.CharField(max_length=10, help_text="UCI format, e.g. e2e4")
    fen_after = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["move_number"]
        unique_together = [("game", "move_number")]

    def __str__(self):
        return f"Game {self.game_id} Move {self.move_number}: {self.san}"


class Donation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="donations")
    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    stripe_payment_intent = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, default="pending")
    message = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"${self.amount} to room {self.room_id}"
