from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ["username", "email", "rating", "games_played", "is_staff"]
    fieldsets = UserAdmin.fieldsets + (
        ("Chess Stats", {"fields": ("rating", "games_played", "games_won", "games_drawn", "avatar")}),
    )
