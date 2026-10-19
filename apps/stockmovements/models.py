from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class StockMovement(WorkspaceModel):
    """
    One change to the stock of a product in a warehouse. Positive quantity is stock in, negative is out.
    Rows are never edited: cancelling a document adds opposite movements.
    """

    class Kind(models.TextChoices):
        PURCHASE = "purchase", "Received from supplier"
        SALE = "sale", "Sold"
        SALE_RETURN = "sale_return", "Returned by customer"
        TRANSFER_OUT = "transfer_out", "Transferred out"
        TRANSFER_IN = "transfer_in", "Transferred in"
        ADJUSTMENT = "adjustment", "Adjusted"
        STOCK_TAKE = "stock_take", "Stock take"
        PRODUCTION_IN = "production_in", "Produced"
        PRODUCTION_OUT = "production_out", "Used in production"
        REVERSAL = "reversal", "Cancelled"

    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="stock_movements")
    warehouse = models.ForeignKey("warehouses.Warehouse", on_delete=models.PROTECT, related_name="stock_movements")
    movement_date = models.DateField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    value = models.DecimalField(**MONEY_FIELD)
    balance_quantity = models.DecimalField(max_digits=14, decimal_places=3, help_text="Stock in the warehouse after this movement")
    source_type = models.CharField(max_length=30)
    source_id = models.UUIDField()
    source_number = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["-movement_date", "-created_at"]
        indexes = [models.Index(fields=["product", "warehouse"]), models.Index(fields=["source_type", "source_id"])]


class StockLevel(WorkspaceModel):
    """What is on hand now, and its weighted average cost, per product and warehouse."""

    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="stock_levels")
    warehouse = models.ForeignKey("warehouses.Warehouse", on_delete=models.CASCADE, related_name="stock_levels")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    average_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        ordering = ["product__name"]
        constraints = [models.UniqueConstraint(fields=["product", "warehouse"], name="one_stock_level_per_place")]
