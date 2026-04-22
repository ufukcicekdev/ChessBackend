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
    queryset = User.objects.order_by("-rating")[:50]


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]


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
