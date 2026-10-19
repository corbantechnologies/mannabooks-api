from django.contrib import admin

from .models import EtimsSubmission


@admin.register(EtimsSubmission)
class EtimsSubmissionAdmin(admin.ModelAdmin):
    list_display = ["document_number", "document_type", "kra_invoice_number", "status", "attempts", "workspace", "created_at"]
    list_filter = ["status", "document_type"]
    search_fields = ["document_number", "workspace__name"]
