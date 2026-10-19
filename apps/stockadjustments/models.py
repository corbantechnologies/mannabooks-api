from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class StockAdjustment(WorkspaceModel):
    """
    A change to stock that isn't a sale or purchase: opening stock, damage, expiry, theft, or stock found.
    Increases and decreases are posted to Stock adjustments and losses (opening stock to Opening balance equity).
    """

    class Reason(models.TextChoices):
        OPENING = "opening", "Opening stock"
        DAMAGED = "damaged", "Damaged"
        EXPIRED = "expired", "Expired"
        THEFT = "theft", "Lost or stolen"
        FOUND = "found", "Found"
        OWN_USE = "own_use", "Used by the business"
        CORRECTION = "correction", "Correction"

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"

    number = models.CharField(max_length=30)
    warehouse = models.ForeignKey("warehouses.Warehouse", on_delete=models.PROTECT, related_name="+")
    adjustment_date = models.DateField()
    reason = models.CharField(max_length=12, choices=Reason.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    total_value = models.DecimalField(**MONEY_FIELD, default=0, help_text="Positive: stock added")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-adjustment_date", "-created_at"]

    def __str__(self):
        return self.number


class StockAdjustmentLine(BaseModel):
    adjustment = models.ForeignKey(StockAdjustment, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, help_text="Positive adds stock, negative removes it")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    value = models.DecimalField(**MONEY_FIELD, default=0)
