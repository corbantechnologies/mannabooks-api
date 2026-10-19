from django.contrib import admin

from .models import LedgerAccount


@admin.register(LedgerAccount)
class LedgerAccountAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'account_type', 'subtype', 'workspace', 'is_active']
    list_filter = ['account_type', 'is_active']
    search_fields = ['code', 'name', 'workspace__name']
