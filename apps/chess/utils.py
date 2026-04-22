from decimal import Decimal


def distribute_donations(game):
    """Maç bitince tamamlanmış bağışları kazanana aktarır. Berabere → yarı yarıya."""
    from .models import Donation, PlatformSettings

    if game.result not in ("white", "black", "draw"):
        return

    donations = list(
        Donation.objects.filter(room=game.room, status="completed").select_related("room")
    )
    if not donations:
        return

    total = sum(d.amount for d in donations)
    if total <= 0:
        return

    fee_percent = PlatformSettings.get().donation_fee_percent
    platform_cut = (total * fee_percent / Decimal("100")).quantize(Decimal("0.01"))
    net = total - platform_cut

    if game.result == "white" and game.white_player:
        game.white_player.wallet_balance += net
        game.white_player.save(update_fields=["wallet_balance"])
    elif game.result == "black" and game.black_player:
        game.black_player.wallet_balance += net
        game.black_player.save(update_fields=["wallet_balance"])
    elif game.result == "draw":
        half = (net / Decimal("2")).quantize(Decimal("0.01"))
        if game.white_player:
            game.white_player.wallet_balance += half
            game.white_player.save(update_fields=["wallet_balance"])
        if game.black_player:
            game.black_player.wallet_balance += half
            game.black_player.save(update_fields=["wallet_balance"])

    Donation.objects.filter(room=game.room, status="completed").update(status="distributed")


def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_ratings(game, k=32):
    """Elo rating update after a finished game."""
    white = game.white_player
    black = game.black_player
    if not white or not black:
        return

    # Don't touch ratings for unfinished/aborted games.
    if game.result in ("ongoing", "aborted"):
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

    distribute_donations(game)
