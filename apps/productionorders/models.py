from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class ProductionOrder(WorkspaceModel):
    """Making a quantity of a product from its recipe. Completing it uses up the components and adds the product at their cost."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=30)
    bom = models.ForeignKey("billsofmaterials.BillOfMaterials", on_delete=models.PROTECT, related_name="production_orders")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, help_text="How much of the product to make")
    warehouse = models.ForeignKey("warehouses.Warehouse", on_delete=models.PROTECT, related_name="+")
    production_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    total_cost = models.DecimalField(**MONEY_FIELD, default=0)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-production_date", "-created_at"]

    def __str__(self):
        return self.number


class ProductionOrderLine(BaseModel):
    order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name="lines")
    component = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, help_text="Planned from the recipe; change it to what was really used")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    value = models.DecimalField(**MONEY_FIELD, default=0)
