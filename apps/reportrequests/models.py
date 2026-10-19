from django.db import models

from apps.core.models import WorkspaceModel


class ReportRequest(WorkspaceModel):
    """
    A manager or supervisor asks people below them for a work report (a weekly sales report, a monthly
    site report...), once or on a schedule. Each round opens one submission per person. `created_by` asks.
    """

    class Frequency(models.TextChoices):
        ONCE = "once", "Once"
        DAILY = "daily", "Every day"
        WEEKLY = "weekly", "Every week"
        MONTHLY = "monthly", "Every month"

    class Audience(models.TextChoices):
        TEAM = "team", "Everyone who reports to me"
        DEPARTMENT = "department", "A department"
        PEOPLE = "people", "People I choose"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    title = models.CharField(max_length=150)
    instructions = models.TextField(blank=True)
    template = models.FileField(upload_to="work-reports/templates/%Y/%m", blank=True)
    template_name = models.CharField(max_length=200, blank=True)
    audience = models.CharField(max_length=12, choices=Audience.choices, default=Audience.TEAM)
    department = models.ForeignKey("departments.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    assignees = models.ManyToManyField("employees.Employee", related_name="report_requests")
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.ONCE)
    first_due_date = models.DateField()
    remind_days_before = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
