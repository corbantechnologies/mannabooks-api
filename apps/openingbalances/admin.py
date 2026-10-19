from django.contrib import admin

from .models import OpeningBalance


@admin.register(OpeningBalance)
class OpeningBalanceAdmin(admin.ModelAdmin):
    list_display = ['workspace', 'as_of_date', 'status']
    list_filter = ['status']
    search_fields = ['workspace__name']
