from django.conf import settings
from django.db import models

from apps.core.documents import PurchaseDocument, PurchaseLine


class PurchaseOrder(PurchaseDocument):
    """An order to a supplier for goods (an LPO). It must be approved before goods can be received against it."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        PARTIALLY_RECEIVED = "partially_received", "Partly received"
        RECEIVED = "received", "Received"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    order_date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    warehouse = models.ForeignKey("warehouses.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                  help_text="Where the goods will be delivered")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-order_date", "-created_at"]


class PurchaseOrderLine(PurchaseLine):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    received_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    billed_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
