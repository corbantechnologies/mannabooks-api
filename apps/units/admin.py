from django.contrib import admin

from .models import Unit


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ["name", "abbreviation", "etims_code", "workspace", "is_active"]
    search_fields = ["name", "abbreviation", "workspace__name"]
