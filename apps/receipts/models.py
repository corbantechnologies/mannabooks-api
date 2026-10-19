from django.db import models

from apps.core.documents import EtimsFields, SalesDocument, SalesLine


class Receipt(SalesDocument, EtimsFields):
    """A cash sale: paid on the spot, posted straight to cash, bank or M-Pesa. No customer needed."""

    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        VOID = "void", "Void"

    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="receipts")
    customer_name = models.CharField(max_length=200, blank=True, help_text="For walk-in customers")
    customer_pin = models.CharField(max_length=20, blank=True, help_text="Walk-in customer's KRA PIN, if they want it on the receipt")
    method = models.CharField(max_length=10, choices=[("cash", "Cash"), ("mpesa", "M-Pesa"), ("bank", "Bank transfer"), ("card", "Card")])
    payment_reference = models.CharField(max_length=60, blank=True)
    deposit_account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    shift = models.ForeignKey("posshifts.PosShift", null=True, blank=True, on_delete=models.PROTECT, related_name="receipts",
                              help_text="Set for sales made at a till")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta(SalesDocument.Meta):
        pass


class ReceiptLine(SalesLine):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="lines")
