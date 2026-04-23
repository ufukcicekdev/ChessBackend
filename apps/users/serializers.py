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
    title = serializers.CharField(read_only=True)
    next_title = serializers.CharField(read_only=True, allow_null=True)
    rating_to_next_title = serializers.IntegerField(read_only=True, allow_null=True)
    masked_iban = serializers.SerializerMethodField(read_only=True)
    username_cooldown_days = serializers.SerializerMethodField(read_only=True)

    def get_username_cooldown_days(self, obj):
        """Returns remaining cooldown days, or 0 if change is allowed."""
        from django.utils import timezone
        from datetime import timedelta
        if not obj.username_changed_at:
            return 0
        remaining = (obj.username_changed_at + timedelta(days=30)) - timezone.now()
        return max(0, remaining.days)

    def get_masked_iban(self, obj):
        iban = obj.iban
        if not iban or len(iban) < 6:
            return iban
        return iban[:2] + "** **** **** " + iban[-4:]

    def validate_iban(self, value):
        if value and not IBAN_RE.match(value.upper()):
            raise serializers.ValidationError("Invalid IBAN format.")
        return value.upper() if value else value

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "rating",
            "title",
            "next_title",
            "rating_to_next_title",
            "games_played", "games_won", "games_drawn", "games_lost",
            "avatar", "created_at",
            "wallet_balance", "iban", "masked_iban",
            "username_cooldown_days",
        ]
        read_only_fields = ["id", "email", "rating", "games_played", "games_won", "games_drawn", "created_at", "wallet_balance"]
        extra_kwargs = {"iban": {"write_only": True}}

    def validate_username(self, value):
        from django.utils import timezone
        from datetime import timedelta
        user = self.instance
        if User.objects.filter(username=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This username is already taken.")
        if len(value) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters.")
        if user.username_changed_at:
            cooldown_end = user.username_changed_at + timedelta(days=30)
            if timezone.now() < cooldown_end:
                days_left = (cooldown_end - timezone.now()).days + 1
                raise serializers.ValidationError(f"You can change your username again in {days_left} day(s).")
        return value

    def update(self, instance, validated_data):
        from django.utils import timezone
        if "username" in validated_data and validated_data["username"] != instance.username:
            instance.username_changed_at = timezone.now()
        return super().update(instance, validated_data)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    pass
