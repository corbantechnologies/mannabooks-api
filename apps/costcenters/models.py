from django.db import models

from apps.core.models import WorkspaceModel


class CostCenter(WorkspaceModel):
    """
    A part of the business whose income and costs are reported on their own: a shop, a vehicle, a farm,
    a donor programme. Documents carry one, and it lands on their income and expense lines in the ledger.
    """

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    department = models.ForeignKey("departments.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code", "name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "code"], name="unique_cost_center_code")]

    def __str__(self):
        return f"{self.code} {self.name}"
