from django.contrib import admin

from .models import DocumentEmail


@admin.register(DocumentEmail)
class DocumentEmailAdmin(admin.ModelAdmin):
    list_display = ("document_number", "to", "status", "workspace", "created_at")
