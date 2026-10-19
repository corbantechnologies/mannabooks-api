from django.conf import settings
from django.db import models

from apps.core.models import WorkspaceModel


class ReportSubmission(WorkspaceModel):
    """One person's report for one round of a request: written, uploaded or both, then accepted or sent back."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        SUBMITTED = "submitted", "Submitted"
        LATE = "late", "Overdue"
        ACCEPTED = "accepted", "Accepted"
        RETURNED = "returned", "Sent back"

    request = models.ForeignKey("reportrequests.ReportRequest", on_delete=models.CASCADE, related_name="submissions")
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="report_submissions")
    period_label = models.CharField(max_length=60, blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    body = models.TextField(blank=True)
    file = models.FileField(upload_to="work-reports/submissions/%Y/%m", blank=True)
    file_name = models.CharField(max_length=200, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_late = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)
    reminded_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-due_date", "employee__first_name"]
        constraints = [models.UniqueConstraint(fields=["request", "employee", "due_date"], name="one_submission_per_round")]

    def __str__(self):
        return f"{self.request} - {self.employee} ({self.due_date})"
