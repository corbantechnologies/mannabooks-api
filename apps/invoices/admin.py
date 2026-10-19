from django.contrib import admin

from .models import Invoice, InvoiceLine


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    raw_id_fields = ["product", "tax_rate", "account"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "issue_date", "total", "balance_due", "status", "etims_status", "workspace"]
    list_filter = ["status", "etims_status"]
    search_fields = ["number", "customer__name", "workspace__name"]
    inlines = [InvoiceLineInline]
