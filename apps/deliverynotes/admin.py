from django.contrib import admin

from .models import DeliveryNote, DeliveryNoteLine


class DeliveryNoteLineInline(admin.TabularInline):
    model = DeliveryNoteLine
    extra = 0
    raw_id_fields = ["product"]


@admin.register(DeliveryNote)
class DeliveryNoteAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "delivery_date", "status", "workspace"]
    list_filter = ["status"]
    search_fields = ["number", "customer__name", "workspace__name"]
    inlines = [DeliveryNoteLineInline]
