import secrets

from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


def new_token() -> str:
    return secrets.token_urlsafe(18)


class OnlineOrder(WorkspaceModel):
    """
    An order placed in the business's online shop by someone outside it. The shop confirms it, gets it ready and
    completes it, which records the cash sale (and takes the stock out). Customers follow it with a private link.
    """

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONFIRMED = "confirmed", "Confirmed"
        READY = "ready", "Ready"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Fulfilment(models.TextChoices):
        PICKUP = "pickup", "Pickup"
        DELIVERY = "delivery", "Delivery"

    class PaymentMethod(models.TextChoices):
        MPESA = "mpesa", "M-Pesa now"
        ON_DELIVERY = "on_delivery", "Pay on pickup or delivery"

    number = models.CharField(max_length=30)
    token = models.CharField(max_length=40, unique=True, default=new_token, help_text="The customer's private link to the order")
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    fulfilment = models.CharField(max_length=10, choices=Fulfilment.choices, default=Fulfilment.PICKUP)
    address = models.TextField(blank=True, help_text="Where to deliver")
    notes = models.TextField(blank=True, help_text="From the customer")
    lines = models.JSONField(default=list, help_text="product_id, name, quantity, unit_price (with VAT), total")
    subtotal = models.DecimalField(**MONEY_FIELD, default=0)
    delivery_fee = models.DecimalField(**MONEY_FIELD, default=0)
    total = models.DecimalField(**MONEY_FIELD, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.ON_DELIVERY)
    mpesa_transaction = models.ForeignKey("mpesatransactions.MpesaTransaction", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    receipt = models.ForeignKey("receipts.Receipt", null=True, blank=True, on_delete=models.SET_NULL, related_name="online_orders",
                                help_text="The cash sale recorded when the order was completed")
    cancel_reason = models.CharField(max_length=255, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["workspace", "number"], name="unique_online_order_number")]

    def __str__(self):
        return f"{self.number} for {self.customer_name}"

    @property
    def payment_status(self) -> str:
        """paid, pending (prompt sent, no answer yet) or unpaid."""
        tx = self.mpesa_transaction
        if tx is not None and tx.status == "completed":
            return "paid"
        if tx is not None and tx.status == "pending":
            return "pending"
        return "unpaid"
