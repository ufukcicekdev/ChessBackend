from django.urls import path
from .views import (
    TournamentListCreateView, TournamentDetailView,
    join_tournament, start_tournament, report_match_result,
    cancel_tournament, leave_tournament, create_match_room,
)

urlpatterns = [
    path("", TournamentListCreateView.as_view(), name="tournaments"),
    path("<uuid:id>/", TournamentDetailView.as_view(), name="tournament-detail"),
    path("<uuid:tournament_id>/join/", join_tournament, name="tournament-join"),
    path("<uuid:tournament_id>/leave/", leave_tournament, name="tournament-leave"),
    path("<uuid:tournament_id>/cancel/", cancel_tournament, name="tournament-cancel"),
    path("<uuid:tournament_id>/start/", start_tournament, name="tournament-start"),
    path("<uuid:tournament_id>/matches/<int:match_number>/room/", create_match_room, name="match-room"),
    path(
        "<uuid:tournament_id>/rounds/<int:match_number>/result/",
        report_match_result,
        name="match-result",
    ),
]
