from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class GoodsReceipt(WorkspaceModel):
    """
    Goods delivered by a supplier (a GRN). Stock items go into the warehouse at the order's cost, and their
    value waits in "Goods received not invoiced" until the supplier's bill arrives.
    """

    class Status(models.TextChoices):
        POSTED = "posted", "Received"
        VOID = "void", "Void"

    number = models.CharField(max_length=30)
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT, related_name="goods_receipts")
    purchase_order = models.ForeignKey("purchaseorders.PurchaseOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="goods_receipts")
    warehouse = models.ForeignKey("warehouses.Warehouse", on_delete=models.PROTECT, related_name="+")
    receipt_date = models.DateField()
    delivery_note_number = models.CharField(max_length=60, blank=True, help_text="The supplier's delivery note")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    total_value = models.DecimalField(**MONEY_FIELD, default=0)
    notes = models.TextField(blank=True)
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-receipt_date", "-created_at"]

    def __str__(self):
        return self.number


class GoodsReceiptLine(BaseModel):
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    order_line = models.ForeignKey("purchaseorders.PurchaseOrderLine", null=True, blank=True, on_delete=models.PROTECT, related_name="receipts")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="+")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, help_text="Before VAT")
    value = models.DecimalField(**MONEY_FIELD)
    stocked = models.BooleanField(default=True, help_text="Went into stock (the product tracks stock)")
    billed_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    line_no = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["line_no"]
