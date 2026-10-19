from django.contrib import admin

from .models import PriceList, PriceListItem


class PriceListItemInline(admin.TabularInline):
    model = PriceListItem
    extra = 0
    raw_id_fields = ["product"]


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ["name", "adjust_percent", "workspace", "is_active"]
    search_fields = ["name", "workspace__name"]
    inlines = [PriceListItemInline]
