from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    rating = models.IntegerField(default=1200)
    games_played = models.IntegerField(default=0)
    games_won = models.IntegerField(default=0)
    games_drawn = models.IntegerField(default=0)
    avatar = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def games_lost(self):
        return self.games_played - self.games_won - self.games_drawn

    def __str__(self):
        return f"{self.username} ({self.rating})"
