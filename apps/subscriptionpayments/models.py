from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.core.money import MONEY_FIELD


class SubscriptionPayment(BaseModel):
    """
    A payment for a business's subscription: an M-Pesa prompt or paybill payment to MannaBooks, or one MannaBooks
    staff record by hand (bank transfer, cheque, a credit or a correction). A completed payment extends `paid_until`.
    """

    class Method(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        BANK = "bank", "Bank transfer"
        CASH = "cash", "Cash"
        CREDIT = "credit", "Credit from MannaBooks"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for M-Pesa"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    subscription = models.ForeignKey("subscriptions.Subscription", on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey("plans.Plan", on_delete=models.PROTECT, related_name="+", help_text="The plan paid for")
    cycle = models.CharField(max_length=8, default="monthly")
    periods = models.PositiveSmallIntegerField(default=1, help_text="Months (monthly) or years (yearly) paid for")
    list_price = models.DecimalField(**MONEY_FIELD, default=0)
    discount = models.DecimalField(**MONEY_FIELD, default=0)
    amount = models.DecimalField(**MONEY_FIELD, help_text="What was charged")
    coupon = models.ForeignKey("coupons.Coupon", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    method = models.CharField(max_length=8, choices=Method.choices, default=Method.MPESA)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reference = models.CharField(max_length=60, blank=True, help_text="M-Pesa code or bank reference")
    mpesa_transaction = models.ForeignKey("mpesatransactions.MpesaTransaction", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    covers_from = models.DateField(null=True, blank=True)
    covers_to = models.DateField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                    help_text="The MannaBooks staff member, for payments recorded by hand")
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subscription.workspace}: {self.amount} ({self.status})"
