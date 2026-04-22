from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.views import CustomTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", lambda request: JsonResponse({"status": "ok"})),
    path("healthz/", lambda request: JsonResponse({"status": "ok"})),
    path("api/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/users/", include("apps.users.urls")),
    path("api/chess/", include("apps.chess.urls")),
    path("api/tournaments/", include("apps.tournaments.urls")),
]
