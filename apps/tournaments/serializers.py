from rest_framework import serializers
from .models import Tournament, TournamentParticipant, TournamentRound, TournamentMatch
from apps.users.serializers import UserPublicSerializer


class TournamentMatchSerializer(serializers.ModelSerializer):
    player1_username = serializers.CharField(source="player1.user.username", default=None)
    player2_username = serializers.CharField(source="player2.user.username", default=None)
    winner_username = serializers.CharField(source="winner.user.username", default=None)
    room_id = serializers.UUIDField(source="room.id", default=None, read_only=True)

    class Meta:
        model = TournamentMatch
        fields = ["match_number", "player1_username", "player2_username", "winner_username", "is_bye", "room_id"]


class TournamentRoundSerializer(serializers.ModelSerializer):
    matches = TournamentMatchSerializer(many=True, read_only=True)

    class Meta:
        model = TournamentRound
        fields = ["round_number", "matches"]


class TournamentParticipantSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username")
    rating = serializers.IntegerField(source="user.rating")
    title = serializers.CharField(source="user.title", read_only=True)

    class Meta:
        model = TournamentParticipant
        fields = ["username", "rating", "title", "seed"]


class TournamentSerializer(serializers.ModelSerializer):
    created_by = UserPublicSerializer(read_only=True)
    winner = UserPublicSerializer(read_only=True)
    rounds = TournamentRoundSerializer(many=True, read_only=True)
    participant_count = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()
    invite_code = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = [
            "id", "name", "description", "time_control", "increment",
            "status", "is_private", "invite_code",
            "registration_start", "registration_end",
            "created_by", "winner", "created_at", "started_at",
            "participant_count", "participants", "rounds",
        ]

    def get_participant_count(self, obj):
        return obj.participants.filter(is_active=True).count()

    def get_participants(self, obj):
        qs = obj.participants.filter(is_active=True).select_related("user").order_by("seed", "id")
        return TournamentParticipantSerializer(qs, many=True).data

    def get_invite_code(self, obj):
        """Only the creator and registered participants can see the invite code."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        if obj.created_by_id == user.id:
            return obj.invite_code
        if obj.participants.filter(user=user, is_active=True).exists():
            return obj.invite_code
        return None


class TournamentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = [
            "name", "description", "time_control", "increment",
            "is_private", "registration_start", "registration_end",
        ]

    def validate(self, attrs):
        start = attrs.get("registration_start")
        end = attrs.get("registration_end")
        if end and start and end <= start:
            raise serializers.ValidationError(
                {"registration_end": "Registration end must be after the start."}
            )
        from django.utils import timezone
        if end and end <= timezone.now():
            raise serializers.ValidationError(
                {"registration_end": "Registration end must be in the future."}
            )
        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        # If registration opens in the future, the tournament starts as "scheduled".
        from django.utils import timezone
        start = validated_data.get("registration_start")
        if start and start > timezone.now():
            validated_data["status"] = Tournament.STATUS_SCHEDULED
        return super().create(validated_data)
