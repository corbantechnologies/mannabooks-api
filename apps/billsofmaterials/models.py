from django.db import models

from apps.core.models import BaseModel, WorkspaceModel


class BillOfMaterials(WorkspaceModel):
    """The recipe for a product the business makes: the components used to make `output_quantity` of it."""

    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="boms")
    name = models.CharField(max_length=120, blank=True)
    output_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product__name"]
        verbose_name_plural = "bills of materials"

    def __str__(self):
        return self.name or f"{self.product} recipe"


class BillOfMaterialsLine(BaseModel):
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name="lines")
    component = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
