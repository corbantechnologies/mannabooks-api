from django.contrib import admin

from .models import RecurringInvoice, RecurringInvoiceLine


class LineInline(admin.TabularInline):
    model = RecurringInvoiceLine
    extra = 0
    raw_id_fields = ["product", "tax_rate"]


@admin.register(RecurringInvoice)
class RecurringInvoiceAdmin(admin.ModelAdmin):
    list_display = ["name", "customer", "frequency", "next_run_date", "status", "workspace"]
    list_filter = ["status", "frequency"]
    inlines = [LineInline]
