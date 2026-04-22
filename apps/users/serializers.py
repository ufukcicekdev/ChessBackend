from rest_framework import serializers
from .models import User


class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "rating", "games_played", "games_won", "games_drawn", "avatar"]


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["username", "email", "password"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserProfileSerializer(serializers.ModelSerializer):
    games_lost = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "rating",
            "games_played", "games_won", "games_drawn", "games_lost",
            "avatar", "created_at",
        ]
        read_only_fields = ["id", "rating", "games_played", "games_won", "games_drawn", "created_at"]
