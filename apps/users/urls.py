from django.urls import path
from .views import RegisterView, ProfileView, LeaderboardView, WithdrawalRequestView, MyRankView, PublicProfileView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/<str:username>/", PublicProfileView.as_view(), name="public-profile"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("leaderboard/my-rank/", MyRankView.as_view(), name="my-rank"),
    path("withdrawals/", WithdrawalRequestView.as_view(), name="withdrawals"),
]
