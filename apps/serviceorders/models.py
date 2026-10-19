from django.conf import settings
from django.db import models

from apps.core.documents import PurchaseDocument, PurchaseLine


class ServiceOrder(PurchaseDocument):
    """Work ordered from a supplier (repairs, cleaning, consultancy). Confirmed done with a service completion."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    order_date = models.DateField()
    required_by = models.DateField(null=True, blank=True)
    scope = models.TextField(blank=True, help_text="What the supplier must do")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-order_date", "-created_at"]


class ServiceOrderLine(PurchaseLine):
    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name="lines")
