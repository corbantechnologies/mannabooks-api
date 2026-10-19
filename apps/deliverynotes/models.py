from django.db import models

from apps.core.models import BaseModel, WorkspaceModel


class DeliveryNote(WorkspaceModel):
    """Goods sent to a customer, signed for on delivery. It records quantities only: no money and no posting."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        DISPATCHED = "dispatched", "Dispatched"
        DELIVERED = "delivered", "Delivered"
        VOID = "void", "Void"

    number = models.CharField(max_length=30)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="delivery_notes")
    invoice = models.ForeignKey("invoices.Invoice", null=True, blank=True, on_delete=models.PROTECT, related_name="delivery_notes")
    delivery_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    delivery_address = models.TextField(blank=True)
    contact_person = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    vehicle = models.CharField(max_length=40, blank=True, help_text="Registration number")
    driver = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.CharField(max_length=120, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-delivery_date", "-created_at"]

    def __str__(self):
        return self.number


class DeliveryNoteLine(BaseModel):
    delivery_note = models.ForeignKey(DeliveryNote, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit = models.CharField(max_length=20, blank=True)
    line_no = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["line_no"]
