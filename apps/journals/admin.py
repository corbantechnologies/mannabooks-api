from django.contrib import admin

from .models import JournalEntry, JournalLine


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    raw_id_fields = ["account", "branch", "department"]


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ["number", "entry_date", "description", "status", "source", "workspace"]
    list_filter = ["status", "source"]
    search_fields = ["number", "description", "reference", "workspace__name"]
    inlines = [JournalLineInline]
