from django.contrib import admin

from .models import StatutoryRate


@admin.register(StatutoryRate)
class StatutoryRateAdmin(admin.ModelAdmin):
    list_display = ["effective_from", "personal_relief", "nssf_upper_limit", "workspace"]
