from rest_framework import generics, permissions, status
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import User
from .serializers import (
    UserRegisterSerializer,
    UserProfileSerializer,
    UserPublicSerializer,
    CustomTokenObtainPairSerializer,
    WithdrawalRequestSerializer,
)


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


class RegisterRateThrottle(AnonRateThrottle):
    scope = "register"


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterRateThrottle]


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class LeaderboardView(generics.ListAPIView):
    serializer_class = UserPublicSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = User.objects.order_by("-rating")
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(username__icontains=q)
        return qs[:50]


class PublicProfileView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, username):
        from django.shortcuts import get_object_or_404
        user = get_object_or_404(User, username=username)
        rank = User.objects.filter(rating__gt=user.rating).count() + 1
        total = User.objects.count()
        data = UserPublicSerializer(user).data
        data["rank"] = rank
        data["total"] = total
        return Response(data)


class MyRankView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            from django.core.cache import cache
            cache_key = f"user_rank_{request.user.id}"
            cached = cache.get(cache_key)
            if cached:
                return Response(cached)
        except Exception:
            cached = None

        rank = User.objects.filter(rating__gt=request.user.rating).count() + 1
        total = User.objects.count()
        data = {"rank": rank, "total": total}

        try:
            cache.set(cache_key, data, timeout=120)
        except Exception:
            pass

        return Response(data)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]


class AvatarUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [__import__("rest_framework.parsers", fromlist=["MultiPartParser"]).MultiPartParser]

    def post(self, request):
        file = request.FILES.get("avatar")
        if not file:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > 5 * 1024 * 1024:
            return Response({"error": "File too large. Max 5 MB."}, status=status.HTTP_400_BAD_REQUEST)
        if not file.content_type.startswith("image/"):
            return Response({"error": "Only image files are allowed."}, status=status.HTTP_400_BAD_REQUEST)

        import os, uuid
        ext = os.path.splitext(file.name)[1].lower() or ".jpg"
        filename = f"avatars/{uuid.uuid4().hex}{ext}"

        from django.core.files.storage import default_storage
        saved_path = default_storage.save(filename, file)
        url = default_storage.url(saved_path)

        request.user.avatar = url
        request.user.save(update_fields=["avatar"])
        return Response({"avatar": url})


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        current = request.data.get("current_password", "")
        new_pw = request.data.get("new_password", "")
        if not current or not new_pw:
            return Response({"error": "Both fields required."}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.check_password(current):
            return Response({"error": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_pw) < 6:
            return Response({"error": "Password must be at least 6 characters."}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new_pw)
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password changed successfully."})


class WithdrawalRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.chess.models import WithdrawalRequest
        qs = WithdrawalRequest.objects.filter(user=request.user).values(
            "id", "amount", "iban_snapshot", "status", "created_at", "processed_at"
        )
        return Response(list(qs))

    def post(self, request):
        from apps.chess.models import WithdrawalRequest
        from django.db import transaction

        serializer = WithdrawalRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if amount > user.wallet_balance:
                return Response({"error": "Insufficient balance."}, status=status.HTTP_400_BAD_REQUEST)
            user.wallet_balance -= amount
            user.save(update_fields=["wallet_balance"])
            wr = WithdrawalRequest.objects.create(
                user=user, amount=amount, iban_snapshot=user.iban
            )

        return Response({"id": str(wr.id), "status": wr.status}, status=status.HTTP_201_CREATED)
