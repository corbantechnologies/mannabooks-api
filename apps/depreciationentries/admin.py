from django.contrib import admin

from .models import DepreciationEntry


@admin.register(DepreciationEntry)
class DepreciationEntryAdmin(admin.ModelAdmin):
    list_display = ("asset", "month_end", "amount", "workspace")
