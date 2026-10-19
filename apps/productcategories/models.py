from django.db import models

from apps.core.models import WorkspaceModel


class ProductCategory(WorkspaceModel):
    """Groups products (e.g. Building materials > Cement) for lists, reports and the till."""

    name = models.CharField(max_length=120)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "product categories"
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_product_category_name")]

    def __str__(self):
        return self.name
