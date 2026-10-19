from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class StockTake(WorkspaceModel):
    """
    A physical count of a warehouse. Starting it lists what the books say; posting it moves each product
    to what was counted, and posts the difference to Stock adjustments and losses.
    """

    class Status(models.TextChoices):
        COUNTING = "counting", "Counting"
        POSTED = "posted", "Posted"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=30)
    warehouse = models.ForeignKey("warehouses.Warehouse", on_delete=models.PROTECT, related_name="+")
    category = models.ForeignKey("productcategories.ProductCategory", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                 help_text="Count only this category; blank counts everything")
    count_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COUNTING)
    difference_value = models.DecimalField(**MONEY_FIELD, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-count_date", "-created_at"]

    def __str__(self):
        return self.number


class StockTakeLine(BaseModel):
    stock_take = models.ForeignKey(StockTake, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="+")
    system_quantity = models.DecimalField(max_digits=14, decimal_places=3, help_text="What the books said when counting started")
    counted_quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True, help_text="Blank: not counted")
    difference = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    value = models.DecimalField(**MONEY_FIELD, default=0)

    class Meta:
        ordering = ["product__name"]
        constraints = [models.UniqueConstraint(fields=["stock_take", "product"], name="one_count_per_product")]
