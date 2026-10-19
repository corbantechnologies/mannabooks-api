from django.db import models

from apps.core.models import WorkspaceModel


class Branch(WorkspaceModel):
    """A location the business operates from (shop, office, warehouse site)."""

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_default", "name"]
        verbose_name_plural = "branches"
        constraints = [models.UniqueConstraint(fields=["workspace", "code"], name="unique_branch_code_per_workspace")]

    def __str__(self):
        return self.name
