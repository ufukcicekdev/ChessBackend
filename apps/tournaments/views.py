from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Tournament, TournamentParticipant, TournamentMatch, TournamentRound
from .serializers import TournamentSerializer, TournamentCreateSerializer
from .services import (
    transition_tournament,
    run_tournament_lifecycle,
    start_tournament_now,
    create_rooms_for_current_round,
)


class TournamentListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        return TournamentCreateSerializer if self.request.method == "POST" else TournamentSerializer

    def get_queryset(self):
        # Lazy fallback so time-based transitions still happen without a beat worker.
        run_tournament_lifecycle()
        qs = (
            Tournament.objects
            .exclude(status=Tournament.STATUS_CANCELLED)
            .prefetch_related("participants", "rounds__matches")
        )
        # Hide private tournaments from the public list, except the user's own
        # (created or joined).
        user = self.request.user
        if user.is_authenticated:
            qs = qs.filter(
                Q(is_private=False)
                | Q(created_by=user)
                | Q(participants__user=user)
            ).distinct()
        else:
            qs = qs.filter(is_private=False)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = TournamentCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        tournament = serializer.save()
        return Response(
            TournamentSerializer(tournament, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TournamentDetailView(generics.RetrieveAPIView):
    queryset = Tournament.objects.prefetch_related("participants__user", "rounds__matches")
    serializer_class = TournamentSerializer
    lookup_field = "id"
    permission_classes = [permissions.AllowAny]

    def get_object(self):
        obj = super().get_object()
        # Lazy transition for this tournament (open registration / auto-start).
        try:
            transition_tournament(obj)
        except Exception:
            pass
        return obj


def _try_join(tournament, user):
    """Shared join logic. Returns (payload_dict, http_status)."""
    # Apply any due transition first (e.g. registration just opened/closed).
    try:
        transition_tournament(tournament)
    except Exception:
        pass

    if tournament.status != Tournament.STATUS_REGISTRATION:
        if tournament.status == Tournament.STATUS_SCHEDULED:
            return {"error": "Registration has not opened yet."}, status.HTTP_400_BAD_REQUEST
        return {"error": "Registration is closed."}, status.HTTP_400_BAD_REQUEST

    now = timezone.now()
    if tournament.registration_start and now < tournament.registration_start:
        return {"error": "Registration has not opened yet."}, status.HTTP_400_BAD_REQUEST
    if tournament.registration_end and now >= tournament.registration_end:
        return {"error": "Registration has closed."}, status.HTTP_400_BAD_REQUEST

    _, created = TournamentParticipant.objects.get_or_create(
        tournament=tournament, user=user
    )
    if not created:
        return {"error": "Already registered."}, status.HTTP_400_BAD_REQUEST
    return {"status": "joined", "tournament_id": str(tournament.id)}, status.HTTP_200_OK


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def join_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    payload, code = _try_join(tournament, request.user)
    return Response(payload, status=code)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def join_by_code(request):
    """Join a tournament using its invite code (works for private tournaments)."""
    code = (request.data.get("code") or "").strip().upper()
    if not code:
        return Response({"error": "Invite code is required."}, status=status.HTTP_400_BAD_REQUEST)
    tournament = Tournament.objects.filter(invite_code=code).first()
    if not tournament:
        return Response({"error": "Invalid invite code."}, status=status.HTTP_404_NOT_FOUND)
    payload, http_status = _try_join(tournament, request.user)
    return Response(payload, status=http_status)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def start_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id, created_by=request.user)
    if tournament.status != Tournament.STATUS_REGISTRATION:
        return Response({"error": "Tournament already started"}, status=status.HTTP_400_BAD_REQUEST)
    if tournament.participants.filter(is_active=True).count() < 2:
        return Response({"error": "Need at least 2 players"}, status=status.HTTP_400_BAD_REQUEST)

    start_tournament_now(tournament)
    return Response(TournamentSerializer(tournament, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def cancel_tournament(request, tournament_id):
    """Creator can cancel a tournament still in registration."""
    tournament = get_object_or_404(Tournament, id=tournament_id, created_by=request.user)
    if tournament.status not in (Tournament.STATUS_SCHEDULED, Tournament.STATUS_REGISTRATION):
        return Response({"error": "Can only cancel before the tournament starts."}, status=status.HTTP_400_BAD_REQUEST)
    tournament.status = Tournament.STATUS_CANCELLED
    tournament.save(update_fields=["status"])
    return Response({"status": "cancelled"})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def leave_tournament(request, tournament_id):
    """Participant can leave during registration."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if tournament.status not in (Tournament.STATUS_SCHEDULED, Tournament.STATUS_REGISTRATION):
        return Response({"error": "Cannot leave after tournament has started."}, status=status.HTTP_400_BAD_REQUEST)
    participant = TournamentParticipant.objects.filter(tournament=tournament, user=request.user).first()
    if not participant:
        return Response({"error": "Not registered."}, status=status.HTTP_400_BAD_REQUEST)
    participant.delete()
    return Response({"status": "left"})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_match_room(request, tournament_id, match_number):
    """
    One of the two players creates a room for their bracket match.
    If a room already exists, returns it directly.
    """
    from apps.chess.models import Room
    tournament = get_object_or_404(Tournament, id=tournament_id, status=Tournament.STATUS_ACTIVE)
    current_round = tournament.rounds.order_by("-round_number").first()
    match = get_object_or_404(TournamentMatch, round=current_round, match_number=match_number)

    # Only the two players can create the room
    my_username = request.user.username
    p1_name = match.player1.user.username if match.player1 else None
    p2_name = match.player2.user.username if match.player2 else None
    if my_username not in (p1_name, p2_name):
        return Response({"error": "You are not a player in this match."}, status=status.HTTP_403_FORBIDDEN)

    if match.is_bye:
        return Response({"error": "Bye match — no room needed."}, status=status.HTTP_400_BAD_REQUEST)

    if match.winner:
        return Response({"error": "Match already finished."}, status=status.HTTP_400_BAD_REQUEST)

    # Return existing room if already created
    if match.room_id:
        return Response({"room_id": str(match.room.id)})

    room = Room.objects.create(
        time_control=tournament.time_control,
        increment=tournament.increment,
        created_by=request.user,
        is_public=False,
    )
    match.room = room
    match.save(update_fields=["room"])
    return Response({"room_id": str(room.id)}, status=status.HTTP_201_CREATED)


def advance_tournament_bracket(game):
    """
    Called after a tournament match game ends.
    Finds the TournamentMatch linked to this room, sets the winner, advances bracket.
    """
    try:
        match = TournamentMatch.objects.select_related(
            "round__tournament", "player1__user", "player2__user"
        ).get(room=game.room)
    except TournamentMatch.DoesNotExist:
        return

    if match.winner:
        return  # already processed

    tournament = match.round.tournament

    # Determine winner participant
    if game.result == "white" and game.white_player:
        winner_user = game.white_player
    elif game.result == "black" and game.black_player:
        winner_user = game.black_player
    elif game.result == "draw":
        # Draw in tournament: higher-seeded player (player1) advances
        winner_user = match.player1.user if match.player1 else None
    else:
        return

    if not winner_user:
        return

    try:
        participant = TournamentParticipant.objects.get(tournament=tournament, user=winner_user)
    except TournamentParticipant.DoesNotExist:
        return

    match.winner = participant
    match.save(update_fields=["winner"])

    # Check if round complete → advance
    current_round = match.round
    round_matches = list(current_round.matches.all())
    if not all(m.winner is not None for m in round_matches):
        return  # round not finished yet

    winners = [m.winner for m in round_matches]
    if len(winners) == 1:
        tournament.winner = winners[0].user
        tournament.status = Tournament.STATUS_FINISHED
        tournament.ended_at = timezone.now()
        tournament.save(update_fields=["winner", "status", "ended_at"])
    else:
        next_round, _ = TournamentRound.objects.get_or_create(
            tournament=tournament,
            round_number=current_round.round_number + 1,
        )
        for i in range(0, len(winners), 2):
            p1 = winners[i]
            p2 = winners[i + 1] if i + 1 < len(winners) else None
            TournamentMatch.objects.get_or_create(
                round=next_round,
                match_number=i // 2 + 1,
                defaults={"player1": p1, "player2": p2},
            )
        # Open rooms for the freshly-created round so players can start immediately.
        create_rooms_for_current_round(tournament)
        # A bye in the new round may already decide a match → cascade.
        _advance_byes(next_round)


def _advance_byes(round_obj):
    """If a newly created round contains bye matches (winner auto-set), and that
    completes the round, advance again. Prevents the bracket stalling on byes."""
    matches = list(round_obj.matches.all())
    if matches and all(m.winner_id is not None for m in matches):
        # Reuse the normal advance path via a synthetic call on any bye match's
        # round completion.
        _complete_round_and_advance(round_obj)


def _complete_round_and_advance(current_round):
    tournament = current_round.tournament
    winners = [m.winner for m in current_round.matches.all()]
    if len(winners) == 1:
        tournament.winner = winners[0].user
        tournament.status = Tournament.STATUS_FINISHED
        tournament.ended_at = timezone.now()
        tournament.save(update_fields=["winner", "status", "ended_at"])
        return
    next_round, _ = TournamentRound.objects.get_or_create(
        tournament=tournament,
        round_number=current_round.round_number + 1,
    )
    for i in range(0, len(winners), 2):
        p1 = winners[i]
        p2 = winners[i + 1] if i + 1 < len(winners) else None
        TournamentMatch.objects.get_or_create(
            round=next_round,
            match_number=i // 2 + 1,
            defaults={"player1": p1, "player2": p2},
        )
    create_rooms_for_current_round(tournament)
    _advance_byes(next_round)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def report_match_result(request, tournament_id, match_number):
    """Record a match winner and advance the bracket."""
    from .models import TournamentMatch, TournamentRound
    tournament = get_object_or_404(Tournament, id=tournament_id, created_by=request.user)
    winner_username = request.data.get("winner")
    if not winner_username:
        return Response({"error": "winner field required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        participant = TournamentParticipant.objects.get(
            tournament=tournament, user__username=winner_username
        )
    except TournamentParticipant.DoesNotExist:
        return Response({"error": "Player not in tournament"}, status=status.HTTP_400_BAD_REQUEST)

    current_round = tournament.rounds.order_by("-round_number").first()
    match = get_object_or_404(TournamentMatch, round=current_round, match_number=match_number)
    match.winner = participant
    match.save(update_fields=["winner"])

    # Check if round is complete and advance winners to next round
    round_matches = current_round.matches.all()
    if all(m.winner is not None for m in round_matches):
        winners = [m.winner for m in round_matches]
        if len(winners) == 1:
            tournament.winner = winners[0].user
            tournament.status = Tournament.STATUS_FINISHED
            tournament.ended_at = timezone.now()
            tournament.save(update_fields=["winner", "status", "ended_at"])
        else:
            next_round = TournamentRound.objects.create(
                tournament=tournament,
                round_number=current_round.round_number + 1,
            )
            for i in range(0, len(winners), 2):
                p1 = winners[i]
                p2 = winners[i + 1] if i + 1 < len(winners) else None
                TournamentMatch.objects.create(
                    round=next_round,
                    match_number=i // 2 + 1,
                    player1=p1,
                    player2=p2,
                )

    return Response(TournamentSerializer(tournament).data)
