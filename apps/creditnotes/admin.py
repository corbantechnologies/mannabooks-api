from django.contrib import admin

from .models import CreditNote


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "invoice", "issue_date", "total", "status", "workspace"]
    list_filter = ["status"]
    search_fields = ["number", "customer__name", "workspace__name"]
