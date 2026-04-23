import json
import stripe
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import Serializer, IntegerField
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from .models import Room, Game, Move, Donation, Challenge
from .serializers import RoomSerializer, RoomCreateSerializer, GameSerializer, GameHistorySummarySerializer, DonationSerializer
from .throttles import DonateRateThrottle
from . import matchmaking

stripe.api_key = settings.STRIPE_SECRET_KEY

STATS_CACHE_KEY = "platform_stats"
STATS_CACHE_TTL = 10  # seconds


def _redis():
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL or "", decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


class RoomListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return RoomCreateSerializer
        return RoomSerializer

    def get_queryset(self):
        qs = Room.objects.select_related("created_by", "game").filter(is_public=True)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
            # "Live games" should not include rooms where the chess game has already ended,
            # even if the room row wasn't updated for some reason.
            if status_filter == Room.STATUS_ACTIVE:
                qs = qs.filter(
                    game__isnull=False,
                    game__white_player__isnull=False,
                    game__black_player__isnull=False,
                    game__result=Game.RESULT_ONGOING,
                    game__moves__isnull=False,  # at least one move made
                ).distinct()
        return qs

    def create(self, request, *args, **kwargs):
        serializer = RoomCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        room = serializer.save()
        return Response(RoomSerializer(room).data, status=status.HTTP_201_CREATED)


class RoomDetailView(generics.RetrieveAPIView):
    queryset = Room.objects.select_related("created_by", "game")
    serializer_class = RoomSerializer
    lookup_field = "id"
    permission_classes = [permissions.AllowAny]


class GameHistoryView(generics.ListAPIView):
    serializer_class = GameHistorySummarySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        username = self.kwargs.get("username")
        return (
            Game.objects.filter(result__in=["white", "black", "draw"])
            .filter(Q(white_player__username=username) | Q(black_player__username=username))
            .select_related("white_player", "black_player", "room")
            .distinct()
            .order_by("-created_at")[:50]
        )


class GameRecentListView(generics.ListAPIView):
    serializer_class = GameHistorySummarySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return (
            Game.objects.filter(result__in=["white", "black", "draw"])
            .select_related("white_player", "black_player", "room")
            .order_by("-ended_at", "-created_at")[:100]
        )


class GameDetailView(generics.RetrieveAPIView):
    queryset = Game.objects.prefetch_related("moves").select_related("white_player", "black_player", "room")
    serializer_class = GameSerializer
    lookup_field = "id"
    permission_classes = [permissions.AllowAny]


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def platform_stats(request):
    r = _redis()
    if r:
        cached = r.get(STATS_CACHE_KEY)
        if cached:
            return Response(json.loads(cached))
    User = get_user_model()
    now = timezone.now()
    recent_cutoff = now - timedelta(minutes=15)

    # Live games: ongoing with both players seated
    live_qs = Game.objects.filter(
        result=Game.RESULT_ONGOING,
        white_player__isnull=False,
        black_player__isnull=False,
    )
    live_games_count = live_qs.count()

    # Players currently in a live game
    live_player_ids: set[int] = set()
    for wid, bid in live_qs.values_list("white_player_id", "black_player_id"):
        live_player_ids.add(wid)
        live_player_ids.add(bid)
    players_in_live_games = len(live_player_ids)

    # Active users = made a move in the last 15 min OR currently in a live game
    recent_move_pairs = (
        Move.objects.filter(timestamp__gte=recent_cutoff)
        .values_list("game__white_player_id", "game__black_player_id")
        .distinct()
    )
    recent_active_ids: set[int] = set(live_player_ids)
    for wid, bid in recent_move_pairs:
        if wid:
            recent_active_ids.add(wid)
        if bid:
            recent_active_ids.add(bid)
    users_active_last_15m = len(recent_active_ids)

    rooms_waiting = Room.objects.filter(status=Room.STATUS_WAITING).count()

    games_finished_today = Game.objects.filter(
        ended_at__date=now.date(),
        result__in=[Game.RESULT_WHITE, Game.RESULT_BLACK, Game.RESULT_DRAW],
    ).count()

    mm_queue = matchmaking.count_matchmaking_queue_entries()

    payload = {
        "live_games": live_games_count,
        "players_in_live_games": players_in_live_games,
        "users_active_last_15m": users_active_last_15m,
        "rooms_waiting": rooms_waiting,
        "games_finished_today": games_finished_today,
        "matchmaking_queue": mm_queue,
        "registered_users": User.objects.count(),
        "active_users_window_minutes": 15,
    }
    if r:
        r.setex(STATS_CACHE_KEY, STATS_CACHE_TTL, json.dumps(payload))
    return Response(payload)


class _MatchmakingSerializer(Serializer):
    time_control = IntegerField(min_value=10)
    increment = IntegerField(min_value=0, required=False, default=0)


class MatchmakingJoinView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = _MatchmakingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            result = matchmaking.join_queue(
                user=request.user,
                time_control=s.validated_data["time_control"],
                increment=s.validated_data["increment"],
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": result.status, "room_id": result.room_id})


class MatchmakingStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        s = _MatchmakingSerializer(data=request.query_params)
        s.is_valid(raise_exception=True)
        try:
            result = matchmaking.status(
                user=request.user,
                time_control=s.validated_data["time_control"],
                increment=s.validated_data["increment"],
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": result.status, "room_id": result.room_id})


class MatchmakingLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = _MatchmakingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            matchmaking.leave_queue(
                user=request.user,
                time_control=s.validated_data["time_control"],
                increment=s.validated_data["increment"],
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "left"})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([DonateRateThrottle])
def create_donation(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    if room.status != Room.STATUS_ACTIVE:
        return Response({"error": "Donations are only allowed for active games."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = DonationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    amount = serializer.validated_data["amount"]
    if amount <= 0:
        return Response({"error": "Amount must be positive."}, status=status.HTTP_400_BAD_REQUEST)
    if amount > 10000:
        return Response({"error": "Amount exceeds maximum allowed."}, status=status.HTTP_400_BAD_REQUEST)

    amount_cents = int(amount * 100)
    currency = serializer.validated_data.get("currency", "usd").lower()

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            metadata={"room_id": str(room_id)},
        )
        donation = Donation.objects.create(
            room=room,
            donor=request.user if request.user.is_authenticated else None,
            amount=serializer.validated_data["amount"],
            currency=currency.upper(),
            message=serializer.validated_data.get("message", ""),
            stripe_payment_intent=intent.id,
            status="pending",
        )
        return Response(
            {
                "client_secret": intent.client_secret,
                "donation_id": str(donation.id),
            },
            status=status.HTTP_201_CREATED,
        )
    except stripe.error.StripeError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ws_ticket(request):
    """Issue a short-lived one-time ticket for WebSocket auth (avoids JWT in URL logs)."""
    import secrets
    r = _redis()
    if not r:
        return Response({"error": "Ticket service unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    ticket = secrets.token_urlsafe(32)
    r.setex(f"ws_ticket:{ticket}", 30, str(request.user.id))
    return Response({"ticket": ticket})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return Response(status=status.HTTP_400_BAD_REQUEST)

    if event["type"] == "payment_intent.succeeded":
        intent_id = event["data"]["object"]["id"]
        Donation.objects.filter(stripe_payment_intent=intent_id).update(status="completed")

    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def platform_features(request):
    """Returns feature flags for the frontend."""
    from .models import PlatformSettings
    s = PlatformSettings.get()
    return Response({
        "paid_challenges_enabled": s.paid_challenges_enabled,
        "challenge_fee_percent": str(s.challenge_fee_percent),
        "challenge_min_wager": str(s.challenge_min_wager),
        "challenge_max_wager": str(s.challenge_max_wager),
    })


# ── Challenge (game invite) endpoints ─────────────────────────────────────────

User = get_user_model()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_challenge(request):
    from .models import PlatformSettings
    username = request.data.get("username")
    time_control = int(request.data.get("time_control", 300))
    increment = int(request.data.get("increment", 0))
    wager_amount = request.data.get("wager_amount")  # None for free challenges

    if not username:
        return Response({"error": "username required"}, status=400)

    try:
        challenged = User.objects.get(username=username)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    if challenged == request.user:
        return Response({"error": "Cannot challenge yourself"}, status=400)

    # Validate paid challenge
    if wager_amount is not None:
        settings_obj = PlatformSettings.get()
        if not settings_obj.paid_challenges_enabled:
            return Response({"error": "Paid challenges are not enabled"}, status=400)
        try:
            wager_amount = float(wager_amount)
        except (TypeError, ValueError):
            return Response({"error": "Invalid wager amount"}, status=400)
        if wager_amount < float(settings_obj.challenge_min_wager):
            return Response({"error": f"Minimum wager is ${settings_obj.challenge_min_wager}"}, status=400)
        if wager_amount > float(settings_obj.challenge_max_wager):
            return Response({"error": f"Maximum wager is ${settings_obj.challenge_max_wager}"}, status=400)
    else:
        wager_amount = None

    # Cancel any existing pending challenge between these two users
    Challenge.objects.filter(
        challenger=request.user, challenged=challenged, status=Challenge.STATUS_PENDING
    ).update(status=Challenge.STATUS_EXPIRED)

    challenge = Challenge.objects.create(
        challenger=request.user,
        challenged=challenged,
        time_control=time_control,
        increment=increment,
        wager_amount=wager_amount,
    )
    return Response({"id": str(challenge.id)}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def accept_challenge(request, challenge_id):
    challenge = get_object_or_404(
        Challenge, id=challenge_id, challenged=request.user, status=Challenge.STATUS_PENDING
    )

    # Expire challenge if older than 60 seconds
    if (timezone.now() - challenge.created_at).total_seconds() > 60:
        challenge.status = Challenge.STATUS_EXPIRED
        challenge.save(update_fields=["status"])
        return Response({"error": "Challenge expired"}, status=400)

    # Create room and assign players
    room = Room.objects.create(
        time_control=challenge.time_control,
        increment=challenge.increment,
        created_by=challenge.challenger,
        is_public=True,
    )
    challenge.status = Challenge.STATUS_ACCEPTED
    challenge.room = room
    challenge.save(update_fields=["status", "room"])

    return Response({"room_id": str(room.id)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decline_challenge(request, challenge_id):
    challenge = get_object_or_404(
        Challenge, id=challenge_id, challenged=request.user, status=Challenge.STATUS_PENDING
    )
    challenge.status = Challenge.STATUS_DECLINED
    challenge.save(update_fields=["status"])
    return Response({"status": "declined"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_challenges(request):
    # Expire old ones first
    cutoff = timezone.now() - timedelta(seconds=60)
    Challenge.objects.filter(
        challenged=request.user, status=Challenge.STATUS_PENDING, created_at__lt=cutoff
    ).update(status=Challenge.STATUS_EXPIRED)

    challenges = Challenge.objects.filter(
        challenged=request.user, status=Challenge.STATUS_PENDING
    ).select_related("challenger")

    data = [
        {
            "id": str(c.id),
            "challenger": c.challenger.username,
            "challenger_rating": getattr(c.challenger, "rating", None),
            "time_control": c.time_control,
            "increment": c.increment,
            "wager_amount": str(c.wager_amount) if c.wager_amount else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in challenges
    ]
    return Response(data)
