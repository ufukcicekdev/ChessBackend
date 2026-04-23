from django.urls import path
from .views import (
    RoomListCreateView, RoomDetailView,
    GameHistoryView, GameRecentListView, GameDetailView,
    create_donation, stripe_webhook, platform_stats, platform_features, ws_ticket,
    MatchmakingJoinView, MatchmakingStatusView, MatchmakingLeaveView,
    send_challenge, accept_challenge, decline_challenge, pending_challenges,
)

urlpatterns = [
    path("stats/", platform_stats, name="chess-stats"),
    path("rooms/", RoomListCreateView.as_view(), name="rooms"),
    path("rooms/<uuid:id>/", RoomDetailView.as_view(), name="room-detail"),
    path("rooms/<uuid:room_id>/donate/", create_donation, name="donate"),
    path("games/recent/", GameRecentListView.as_view(), name="games-recent"),
    path("games/<uuid:id>/", GameDetailView.as_view(), name="game-detail"),
    path("history/<str:username>/", GameHistoryView.as_view(), name="game-history"),
    path("matchmaking/join/", MatchmakingJoinView.as_view(), name="matchmaking-join"),
    path("matchmaking/status/", MatchmakingStatusView.as_view(), name="matchmaking-status"),
    path("matchmaking/leave/", MatchmakingLeaveView.as_view(), name="matchmaking-leave"),
    path("ws-ticket/", ws_ticket, name="ws-ticket"),
    path("features/", platform_features, name="platform-features"),
    path("webhook/stripe/", stripe_webhook, name="stripe-webhook"),
    path("challenges/", send_challenge, name="challenge-send"),
    path("challenges/pending/", pending_challenges, name="challenge-pending"),
    path("challenges/<uuid:challenge_id>/accept/", accept_challenge, name="challenge-accept"),
    path("challenges/<uuid:challenge_id>/decline/", decline_challenge, name="challenge-decline"),
]
