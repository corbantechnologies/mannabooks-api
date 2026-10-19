from django.contrib import admin

from .models import ReportSubmission


@admin.register(ReportSubmission)
class ReportSubmissionAdmin(admin.ModelAdmin):
    list_display = ("request", "employee", "due_date", "status")
