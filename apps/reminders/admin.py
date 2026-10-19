from django.contrib import admin

from .models import ReminderLog, ReminderRule


@admin.register(ReminderRule)
class ReminderRuleAdmin(admin.ModelAdmin):
    list_display = ["name", "days", "is_active", "workspace"]


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ["invoice", "sent_to", "rule", "error", "created_at"]
