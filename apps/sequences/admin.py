from django.contrib import admin

from .models import Sequence


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    list_display = ["key", "workspace", "prefix", "next_number", "include_year"]
    search_fields = ["key", "workspace__name"]
