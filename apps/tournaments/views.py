from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Tournament, TournamentParticipant
from .serializers import TournamentSerializer, TournamentCreateSerializer


class TournamentListCreateView(generics.ListCreateAPIView):
    queryset = Tournament.objects.prefetch_related("participants", "rounds__matches")
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        return TournamentCreateSerializer if self.request.method == "POST" else TournamentSerializer

    def create(self, request, *args, **kwargs):
        serializer = TournamentCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        tournament = serializer.save()
        return Response(TournamentSerializer(tournament).data, status=status.HTTP_201_CREATED)


class TournamentDetailView(generics.RetrieveAPIView):
    queryset = Tournament.objects.prefetch_related("participants__user", "rounds__matches")
    serializer_class = TournamentSerializer
    lookup_field = "id"
    permission_classes = [permissions.AllowAny]


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def join_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if tournament.status != Tournament.STATUS_REGISTRATION:
        return Response({"error": "Registration is closed"}, status=status.HTTP_400_BAD_REQUEST)
    if tournament.participants.filter(is_active=True).count() >= tournament.max_players:
        return Response({"error": "Tournament is full"}, status=status.HTTP_400_BAD_REQUEST)

    _, created = TournamentParticipant.objects.get_or_create(
        tournament=tournament, user=request.user
    )
    if not created:
        return Response({"error": "Already registered"}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"status": "joined"})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def start_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id, created_by=request.user)
    if tournament.status != Tournament.STATUS_REGISTRATION:
        return Response({"error": "Tournament already started"}, status=status.HTTP_400_BAD_REQUEST)
    if tournament.participants.filter(is_active=True).count() < 2:
        return Response({"error": "Need at least 2 players"}, status=status.HTTP_400_BAD_REQUEST)

    tournament.status = Tournament.STATUS_ACTIVE
    tournament.started_at = timezone.now()
    tournament.save(update_fields=["status", "started_at"])
    tournament.generate_bracket()

    return Response(TournamentSerializer(tournament).data)


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
