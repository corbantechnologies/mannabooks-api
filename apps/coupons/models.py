from django.db import models

from apps.core.models import BaseModel
from apps.core.money import MONEY_FIELD


class Coupon(BaseModel):
    """A discount code a business enters when it pays, e.g. LAUNCH50 for 50% off the first three months."""

    code = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=255, blank=True)
    percent_off = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount_off = models.DecimalField(**MONEY_FIELD, default=0, help_text="KES off each payment (after any percentage)")
    payments = models.PositiveSmallIntegerField(null=True, blank=True, help_text="How many payments it applies to; blank: every payment")
    plans = models.ManyToManyField("plans.Plan", blank=True, related_name="+", help_text="Blank: every paid plan")
    valid_until = models.DateField(null=True, blank=True)
    max_redemptions = models.PositiveIntegerField(null=True, blank=True)
    times_redeemed = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code
