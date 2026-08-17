from django.urls import path
from .views import RegisterView, ProfileView, LeaderboardView, WithdrawalRequestView, MyRankView, PublicProfileView, ChangePasswordView, AvatarUploadView, FCMTokenView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("fcm-token/", FCMTokenView.as_view(), name="fcm-token"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/<str:username>/", PublicProfileView.as_view(), name="public-profile"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("leaderboard/my-rank/", MyRankView.as_view(), name="my-rank"),
    path("withdrawals/", WithdrawalRequestView.as_view(), name="withdrawals"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("avatar/", AvatarUploadView.as_view(), name="avatar-upload"),
]
