from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class StockTransfer(WorkspaceModel):
    """Stock moved from one warehouse to another, at its average cost. Saving it moves the stock."""

    class Status(models.TextChoices):
        POSTED = "posted", "Moved"
        VOID = "void", "Void"

    number = models.CharField(max_length=30)
    from_warehouse = models.ForeignKey("warehouses.Warehouse", on_delete=models.PROTECT, related_name="+")
    to_warehouse = models.ForeignKey("warehouses.Warehouse", on_delete=models.PROTECT, related_name="+")
    transfer_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    total_value = models.DecimalField(**MONEY_FIELD, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-transfer_date", "-created_at"]

    def __str__(self):
        return self.number


class StockTransferLine(BaseModel):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
