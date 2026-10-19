from django.contrib import admin

from .models import ExchangeRate


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ['currency', 'rate_date', 'rate', 'workspace']
    list_filter = []
    search_fields = ['currency__code', 'workspace__name']
