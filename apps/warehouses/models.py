from django.db import models

from apps.core.models import WorkspaceModel


class Warehouse(WorkspaceModel):
    """A place stock is kept: a store, a shop floor, a van."""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                               help_text="Sales at this branch take stock from here")
    address = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_default", "name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_warehouse_name")]

    def __str__(self):
        return self.name
