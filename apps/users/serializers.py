import re
from decimal import Decimal

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User

IBAN_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}$")


class UserPublicSerializer(serializers.ModelSerializer):
    title = serializers.CharField(read_only=True)
    next_title = serializers.CharField(read_only=True, allow_null=True)
    rating_to_next_title = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "rating",
            "title",
            "next_title",
            "rating_to_next_title",
            "games_played",
            "games_won",
            "games_drawn",
            "avatar",
        ]


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["username", "email", "password"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class WithdrawalRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("1.00"))

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.iban:
            raise serializers.ValidationError("Please add your IBAN before requesting a withdrawal.")
        if attrs["amount"] > user.wallet_balance:
            raise serializers.ValidationError("Insufficient balance.")
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    games_lost = serializers.IntegerField(read_only=True)

    def validate_iban(self, value):
        if value and not IBAN_RE.match(value.upper()):
            raise serializers.ValidationError("Invalid IBAN format.")
        return value.upper() if value else value
    title = serializers.CharField(read_only=True)
    next_title = serializers.CharField(read_only=True, allow_null=True)
    rating_to_next_title = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "rating",
            "title",
            "next_title",
            "rating_to_next_title",
            "games_played", "games_won", "games_drawn", "games_lost",
            "avatar", "created_at",
            "wallet_balance", "iban",
        ]
        read_only_fields = ["id", "rating", "games_played", "games_won", "games_drawn", "created_at", "wallet_balance"]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    pass
