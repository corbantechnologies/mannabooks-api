from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class MpesaTransaction(WorkspaceModel):
    """
    An M-Pesa payment seen through Daraja: an STK prompt MannaBooks sent, or money paid straight to the
    paybill or till (C2B). Completed payments are matched to a customer payment or a cash sale.
    """

    class Kind(models.TextChoices):
        STK = "stk", "Payment prompt"
        C2B = "c2b", "Paid to paybill or till"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for the customer"
        COMPLETED = "completed", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled by the customer"

    kind = models.CharField(max_length=4, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    phone = models.CharField(max_length=20, blank=True)
    payer_name = models.CharField(max_length=120, blank=True)
    amount = models.DecimalField(**MONEY_FIELD)
    mpesa_receipt = models.CharField(max_length=30, blank=True, help_text="M-Pesa transaction code")
    account_reference = models.CharField(max_length=40, blank=True, help_text="Account number the customer entered, or ours")
    checkout_request_id = models.CharField(max_length=80, blank=True)
    result_code = models.CharField(max_length=10, blank=True)
    result_description = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    invoice = models.ForeignKey("invoices.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="mpesa_transactions")
    payment = models.ForeignKey("payments.Payment", null=True, blank=True, on_delete=models.SET_NULL, related_name="mpesa_transactions")
    receipt = models.ForeignKey("receipts.Receipt", null=True, blank=True, on_delete=models.SET_NULL, related_name="mpesa_transactions")
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["checkout_request_id"]), models.Index(fields=["workspace", "status"])]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "mpesa_receipt"], condition=~models.Q(mpesa_receipt=""), name="unique_mpesa_receipt"),
        ]

    def __str__(self):
        return self.mpesa_receipt or f"{self.get_kind_display()} {self.amount}"

    @property
    def is_matched(self) -> bool:
        return bool(self.payment_id or self.receipt_id)
