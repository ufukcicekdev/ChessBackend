from django.urls import path
from .views import (
    TournamentListCreateView, TournamentDetailView,
    join_tournament, start_tournament, report_match_result,
)

urlpatterns = [
    path("", TournamentListCreateView.as_view(), name="tournaments"),
    path("<uuid:id>/", TournamentDetailView.as_view(), name="tournament-detail"),
    path("<uuid:tournament_id>/join/", join_tournament, name="tournament-join"),
    path("<uuid:tournament_id>/start/", start_tournament, name="tournament-start"),
    path(
        "<uuid:tournament_id>/rounds/<int:match_number>/result/",
        report_match_result,
        name="match-result",
    ),
]
