from django.contrib import admin

from .models import LoyaltyMember


@admin.register(LoyaltyMember)
class LoyaltyMemberAdmin(admin.ModelAdmin):
    list_display = ["card_number", "customer", "tier", "points_balance", "workspace"]
