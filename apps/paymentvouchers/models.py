from django.conf import settings
from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class PaymentVoucher(WorkspaceModel):
    """A request to pay a supplier's bills. Someone with approval rights approves it; paying it records the supplier payment."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Awaiting approval"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=30)
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT, related_name="payment_vouchers")
    voucher_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    total = models.DecimalField(**MONEY_FIELD, default=0, help_text="Bills being settled")
    withholding_amount = models.DecimalField(**MONEY_FIELD, default=0)
    notes = models.TextField(blank=True, help_text="Why this payment is due")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    payment = models.ForeignKey("supplierpayments.SupplierPayment", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-voucher_date", "-created_at"]

    def __str__(self):
        return self.number

    @property
    def net_payable(self):
        return self.total - self.withholding_amount


class PaymentVoucherLine(BaseModel):
    voucher = models.ForeignKey(PaymentVoucher, on_delete=models.CASCADE, related_name="lines")
    bill = models.ForeignKey("bills.Bill", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(**MONEY_FIELD)
