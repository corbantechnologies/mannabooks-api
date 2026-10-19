from django.contrib import admin

from .models import LoyaltyProgram


@admin.register(LoyaltyProgram)
class LoyaltyProgramAdmin(admin.ModelAdmin):
    list_display = ["name", "workspace", "is_active", "spend_per_point", "point_value"]
