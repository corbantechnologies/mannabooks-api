from django.contrib import admin

from .models import PosShift


@admin.register(PosShift)
class PosShiftAdmin(admin.ModelAdmin):
    list_display = ["number", "register", "cashier", "status", "opened_at", "cash_difference", "workspace"]
    list_filter = ["status"]
