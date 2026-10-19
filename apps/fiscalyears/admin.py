from django.contrib import admin

from .models import FiscalYear


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'status', 'workspace']
    list_filter = ['status']
    search_fields = ['name', 'workspace__name']
