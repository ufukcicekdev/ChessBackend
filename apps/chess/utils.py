from decimal import Decimal

from django.db import transaction


def distribute_donations(game):
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
    """Elo rating update. DB lock + ratings_updated flag prevent double-execution."""
    from django.contrib.auth import get_user_model
    from .models import Game

    if game.result in ("ongoing", "aborted"):
        return
    if not game.white_player_id or not game.black_player_id:
        return

    with transaction.atomic():
        # Atomically claim the right to update: flip ratings_updated False→True.
        # If another consumer already flipped it, updated=0 and we bail out.
        updated = Game.objects.filter(pk=game.pk, ratings_updated=False).update(
            ratings_updated=True
        )
        if updated == 0:
            return  # already processed by a concurrent consumer

        User = get_user_model()
        players = {
            p.id: p
            for p in User.objects.select_for_update().filter(
                id__in=[game.white_player_id, game.black_player_id]
            )
        }
        white = players.get(game.white_player_id)
        black = players.get(game.black_player_id)
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

    distribute_donations(game)
