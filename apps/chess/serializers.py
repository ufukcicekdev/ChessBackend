from rest_framework import serializers
from .models import Room, Game, Move, Donation
from apps.users.serializers import UserPublicSerializer


class MoveSerializer(serializers.ModelSerializer):
    class Meta:
        model = Move
        fields = ["move_number", "san", "uci", "fen_after", "timestamp"]


class GameSerializer(serializers.ModelSerializer):
    white_player = UserPublicSerializer(read_only=True)
    black_player = UserPublicSerializer(read_only=True)
    moves = MoveSerializer(many=True, read_only=True)
    move_count = serializers.IntegerField(source="moves.count", read_only=True)
    room_id = serializers.UUIDField(read_only=True)
    time_control = serializers.IntegerField(source="room.time_control", read_only=True)
    increment = serializers.IntegerField(source="room.increment", read_only=True)

    class Meta:
        model = Game
        fields = [
            "id", "room_id", "white_player", "black_player",
            "fen", "pgn", "result",
            "white_time_remaining", "black_time_remaining",
            "time_control", "increment",
            "started_at", "ended_at", "moves", "move_count",
        ]


class GameHistorySummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for history/recent lists — no full move list."""
    white_player = UserPublicSerializer(read_only=True)
    black_player = UserPublicSerializer(read_only=True)
    move_count = serializers.IntegerField(source="moves.count", read_only=True)
    time_control = serializers.IntegerField(source="room.time_control", read_only=True)
    increment = serializers.IntegerField(source="room.increment", read_only=True)

    class Meta:
        model = Game
        fields = [
            "id", "white_player", "black_player",
            "result", "white_time_remaining", "black_time_remaining",
            "time_control", "increment", "started_at", "ended_at", "move_count",
        ]


class GameSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for room lists — no full move list."""
    white_player = UserPublicSerializer(read_only=True)
    black_player = UserPublicSerializer(read_only=True)
    move_count = serializers.IntegerField(source="moves.count", read_only=True)
    room_id = serializers.UUIDField(read_only=True)
    time_control = serializers.IntegerField(source="room.time_control", read_only=True)
    increment = serializers.IntegerField(source="room.increment", read_only=True)

    class Meta:
        model = Game
        fields = [
            "id", "room_id", "white_player", "black_player",
            "result", "white_time_remaining", "black_time_remaining",
            "time_control", "increment", "started_at", "move_count",
        ]


class RoomSerializer(serializers.ModelSerializer):
    created_by = UserPublicSerializer(read_only=True)
    game = GameSummarySerializer(read_only=True)
    spectator_count = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            "id", "name", "is_public", "time_control", "increment",
            "status", "created_by", "created_at", "game", "spectator_count",
        ]

    def get_spectator_count(self, obj):
        # Real count comes from channel layer; this is a placeholder
        return 0


class RoomCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["name", "is_public", "time_control", "increment"]

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class DonationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donation
        fields = ["id", "amount", "currency", "message", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]

    def validate_message(self, value):
        # Strip HTML tags — plain text only
        import re
        return re.sub(r"<[^>]+>", "", value).strip()
