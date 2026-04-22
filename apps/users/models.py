from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    rating = models.IntegerField(default=1200)
    games_played = models.IntegerField(default=0)
    games_won = models.IntegerField(default=0)
    games_drawn = models.IntegerField(default=0)
    avatar = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Thresholds are inclusive minimum ratings for a title, ordered highest -> lowest.
    TITLE_THRESHOLDS = [
        (2600, "Super Grandmaster"),
        (2500, "Grandmaster"),
        (2400, "International Master"),
        (2300, "FIDE Master"),
        (2200, "Candidate Master"),
        (2000, "Expert"),
        (1800, "Class A"),
        (1600, "Class B"),
        (1400, "Class C"),
        (1200, "Class D"),
        (1000, "Novice"),
        (0, "Beginner"),
    ]

    @property
    def title(self) -> str:
        r = int(self.rating or 0)
        for min_rating, name in self.TITLE_THRESHOLDS:
            if r >= min_rating:
                return name
        return "Beginner"

    @property
    def next_title(self) -> str | None:
        r = int(self.rating or 0)
        asc = list(reversed(self.TITLE_THRESHOLDS))  # lowest -> highest
        current = None
        for min_rating, name in asc:
            if r >= min_rating:
                current = (min_rating, name)
                break
        if not current:
            return asc[1][1] if len(asc) > 1 else None

        idx = asc.index(current)
        if idx == len(asc) - 1:
            return None
        return asc[idx + 1][1]

    @property
    def rating_to_next_title(self) -> int | None:
        r = int(self.rating or 0)
        asc = list(reversed(self.TITLE_THRESHOLDS))  # lowest -> highest
        current = None
        for min_rating, name in asc:
            if r >= min_rating:
                current = (min_rating, name)
                break
        if not current:
            return asc[1][0] - r if len(asc) > 1 else None

        idx = asc.index(current)
        if idx == len(asc) - 1:
            return None
        next_min = asc[idx + 1][0]
        return max(0, next_min - r)

    @property
    def games_lost(self):
        return self.games_played - self.games_won - self.games_drawn

    def __str__(self):
        return f"{self.username} ({self.rating})"
