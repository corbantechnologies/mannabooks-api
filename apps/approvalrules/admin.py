from django.contrib import admin

from .models import ApprovalRule


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "document_type", "workspace", "min_amount", "max_amount")
