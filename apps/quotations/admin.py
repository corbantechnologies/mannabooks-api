from django.contrib import admin

from .models import Quotation


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "issue_date", "valid_until", "total", "status", "workspace"]
    list_filter = ["status"]
    search_fields = ["number", "customer__name", "workspace__name"]
