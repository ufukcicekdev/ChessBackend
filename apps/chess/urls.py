from django.urls import path
from .views import (
    RoomListCreateView, RoomDetailView,
    GameHistoryView, GameDetailView,
    create_donation, stripe_webhook,
)

urlpatterns = [
    path("rooms/", RoomListCreateView.as_view(), name="rooms"),
    path("rooms/<uuid:id>/", RoomDetailView.as_view(), name="room-detail"),
    path("rooms/<uuid:room_id>/donate/", create_donation, name="donate"),
    path("games/<uuid:id>/", GameDetailView.as_view(), name="game-detail"),
    path("history/<str:username>/", GameHistoryView.as_view(), name="game-history"),
    path("webhook/stripe/", stripe_webhook, name="stripe-webhook"),
]
