from django.contrib import admin

from .models import LoyaltyTier


@admin.register(LoyaltyTier)
class LoyaltyTierAdmin(admin.ModelAdmin):
    list_display = ["name", "min_points", "multiplier", "workspace"]
