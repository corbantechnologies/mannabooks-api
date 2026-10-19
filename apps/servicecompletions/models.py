from django.conf import settings
from django.db import models

from apps.core.models import WorkspaceModel


class ServiceCompletion(WorkspaceModel):
    """Confirmation that a supplier finished the work on a service order, so their bill can be paid."""

    number = models.CharField(max_length=30)
    service_order = models.OneToOneField("serviceorders.ServiceOrder", on_delete=models.PROTECT, related_name="completion")
    completion_date = models.DateField()
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    rating = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1 (poor) to 5 (excellent)")
    notes = models.TextField(blank=True, help_text="What was done, and anything outstanding")

    class Meta:
        ordering = ["-completion_date", "-created_at"]

    def __str__(self):
        return self.number
