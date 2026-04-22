from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User


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


class UserProfileSerializer(serializers.ModelSerializer):
    games_lost = serializers.IntegerField(read_only=True)
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
        ]
        read_only_fields = ["id", "rating", "games_played", "games_won", "games_drawn", "created_at"]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Records last_login so platform stats (recently active users) stay meaningful."""

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        return data
