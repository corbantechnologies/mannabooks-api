from django.conf import settings
from django.db import models

from apps.core.models import WorkspaceModel


class FiscalYear(WorkspaceModel):
    """A financial year of 12 accounting periods. Closing it moves the year's profit to retained earnings."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-start_date"]
        constraints = [models.UniqueConstraint(fields=["workspace", "start_date"], name="unique_fiscal_year_start")]

    def __str__(self):
        return self.name
