def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_ratings(game, k=32):
    """Elo rating update after a finished game."""
    white = game.white_player
    black = game.black_player
    if not white or not black:
        return

    ea = expected_score(white.rating, black.rating)
    eb = 1 - ea

    if game.result == "white":
        sa, sb = 1, 0
    elif game.result == "black":
        sa, sb = 0, 1
    else:
        sa, sb = 0.5, 0.5

    white.rating = max(100, round(white.rating + k * (sa - ea)))
    black.rating = max(100, round(black.rating + k * (sb - eb)))

    white.games_played += 1
    black.games_played += 1
    if game.result == "white":
        white.games_won += 1
    elif game.result == "black":
        black.games_won += 1
    else:
        white.games_drawn += 1
        black.games_drawn += 1

    white.save(update_fields=["rating", "games_played", "games_won", "games_drawn"])
    black.save(update_fields=["rating", "games_played", "games_won", "games_drawn"])
