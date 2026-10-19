from django.db import models

from apps.core.documents import EtimsFields, SalesDocument, SalesLine
from apps.core.money import MONEY_FIELD


class CreditNote(SalesDocument, EtimsFields):
    """Reduces what a customer owes (returns, overcharges, discounts after the sale)."""

    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        VOID = "void", "Void"

    invoice = models.ForeignKey("invoices.Invoice", null=True, blank=True, on_delete=models.PROTECT, related_name="credit_notes")
    reason = models.CharField(max_length=255)
    return_stock = models.BooleanField(default=True, help_text="Put stock items on the note back into stock")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)
    applied_amount = models.DecimalField(**MONEY_FIELD, default=0, help_text="Applied to the invoice")
    unapplied_amount = models.DecimalField(**MONEY_FIELD, default=0, help_text="Left as credit for the customer")
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta(SalesDocument.Meta):
        pass


class CreditNoteLine(SalesLine):
    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name="lines")
