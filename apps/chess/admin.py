from django.contrib import admin
from django.utils import timezone
from .models import Room, Game, Move, Donation, PlatformSettings, WithdrawalRequest, Challenge


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


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ["donation_fee_percent"]

    def has_add_permission(self, request):
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ["user", "amount", "iban_snapshot", "status", "created_at", "processed_at"]
    list_filter = ["status"]
    readonly_fields = ["user", "amount", "iban_snapshot", "created_at"]
    actions = ["mark_paid", "mark_rejected"]

    @admin.action(description="Seçilenleri ödendi olarak işaretle")
    def mark_paid(self, request, queryset):
        queryset.filter(status=WithdrawalRequest.STATUS_PENDING).update(
            status=WithdrawalRequest.STATUS_PAID, processed_at=timezone.now()
        )

    @admin.action(description="Seçilenleri reddet")
    def mark_rejected(self, request, queryset):
        queryset.filter(status=WithdrawalRequest.STATUS_PENDING).update(
            status=WithdrawalRequest.STATUS_REJECTED, processed_at=timezone.now()
        )


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ["id", "challenger", "challenged", "status", "time_control", "increment", "wager_amount", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["id", "challenger", "challenged", "room", "created_at"]
    search_fields = ["challenger__username", "challenged__username"]
