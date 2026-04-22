from rest_framework import serializers
from .models import Tournament, TournamentParticipant, TournamentRound, TournamentMatch
from apps.users.serializers import UserPublicSerializer


class TournamentMatchSerializer(serializers.ModelSerializer):
    player1_username = serializers.CharField(source="player1.user.username", default=None)
    player2_username = serializers.CharField(source="player2.user.username", default=None)
    winner_username = serializers.CharField(source="winner.user.username", default=None)

    class Meta:
        model = TournamentMatch
        fields = ["match_number", "player1_username", "player2_username", "winner_username", "is_bye"]


class TournamentRoundSerializer(serializers.ModelSerializer):
    matches = TournamentMatchSerializer(many=True, read_only=True)

    class Meta:
        model = TournamentRound
        fields = ["round_number", "matches"]


class TournamentSerializer(serializers.ModelSerializer):
    created_by = UserPublicSerializer(read_only=True)
    winner = UserPublicSerializer(read_only=True)
    rounds = TournamentRoundSerializer(many=True, read_only=True)
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = [
            "id", "name", "description", "max_players", "time_control", "increment",
            "status", "created_by", "winner", "created_at", "started_at",
            "participant_count", "rounds",
        ]

    def get_participant_count(self, obj):
        return obj.participants.filter(is_active=True).count()


class TournamentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = ["name", "description", "max_players", "time_control", "increment"]

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)
