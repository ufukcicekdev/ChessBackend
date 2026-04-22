from django.contrib import admin
from .models import Room, Game, Move, Donation


class MoveInline(admin.TabularInline):
    model = Move
    extra = 0
    readonly_fields = ["move_number", "san", "uci", "fen_after", "timestamp"]


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ["id", "white_player", "black_player", "result", "created_at"]
    inlines = [MoveInline]
    readonly_fields = ["id", "pgn", "fen", "created_at"]


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "status", "is_public", "created_by", "created_at"]
    list_filter = ["status", "is_public"]


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ["id", "room", "donor", "amount", "currency", "status", "created_at"]
