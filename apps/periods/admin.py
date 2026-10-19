from django.contrib import admin

from .models import AccountingPeriod


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    list_display = ['name', 'fiscal_year', 'status', 'workspace']
    list_filter = ['status']
    search_fields = ['name', 'workspace__name']
