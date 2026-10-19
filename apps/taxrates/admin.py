from django.contrib import admin

from .models import TaxRate


@admin.register(TaxRate)
class TaxRateAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'kind', 'rate', 'etims_code', 'workspace', 'is_active']
    list_filter = ['kind', 'is_active']
    search_fields = ['code', 'name', 'workspace__name']
