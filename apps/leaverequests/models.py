from django.conf import settings
from django.db import models

from apps.core.models import WorkspaceModel


class LeaveRequest(WorkspaceModel):
    """Time off asked for by an employee and decided by their supervisor (or the department head, or HR)."""

    class Type(models.TextChoices):
        ANNUAL = "annual", "Annual leave"
        SICK = "sick", "Sick leave"
        MATERNITY = "maternity", "Maternity leave"
        PATERNITY = "paternity", "Paternity leave"
        COMPASSIONATE = "compassionate", "Compassionate leave"
        STUDY = "study", "Study leave"
        UNPAID = "unpaid", "Unpaid leave"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.CharField(max_length=15, choices=Type.choices, default=Type.ANNUAL)
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.DecimalField(max_digits=5, decimal_places=1, help_text="Working days (Monday to Friday)")
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-start_date"]
        indexes = [models.Index(fields=["employee", "status"])]

    def __str__(self):
        return f"{self.employee} {self.get_leave_type_display()} {self.start_date}"
