from django.contrib import admin
from .models import Tournament, TournamentParticipant, TournamentRound, TournamentMatch


class TournamentMatchInline(admin.TabularInline):
    model = TournamentMatch
    extra = 0


class TournamentRoundInline(admin.StackedInline):
    model = TournamentRound
    extra = 0


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "max_players", "created_by", "created_at"]
    inlines = [TournamentRoundInline]
