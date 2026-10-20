from django.db import models

from apps.core.models import BaseModel


class Subscription(BaseModel):
    """
    A business's plan and where it stands with paying for it. Every workspace has exactly one.

    trialing -> (trial ends) -> active on the free plan, or on a paid plan once paid
    active -> (paid period ends unpaid) -> past_due -> (grace ends) -> read_only (can look and export, not change)
    """

    class Status(models.TextChoices):
        TRIALING = "trialing", "Trial"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Payment due"
        READ_ONLY = "read_only", "Read only (unpaid)"
        CANCELLED = "cancelled", "Cancelled"

    class Cycle(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    workspace = models.OneToOneField("workspaces.Workspace", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey("plans.Plan", on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRIALING)
    cycle = models.CharField(max_length=8, choices=Cycle.choices, default=Cycle.MONTHLY)
    account_number = models.CharField(max_length=12, unique=True, help_text="Paybill account number for this business, e.g. MB104233")
    trial_ends_on = models.DateField(null=True, blank=True)
    paid_until = models.DateField(null=True, blank=True, help_text="The last day already paid for")
    complimentary = models.BooleanField(default=False, help_text="No payments needed (pilot and founding businesses, partners)")
    complimentary_until = models.DateField(null=True, blank=True, help_text="Complimentary ends after this day; blank: until staff end it")
    reminders_sent = models.JSONField(default=list, blank=True, help_text="Reminder emails already sent, e.g. due-7:2026-11-30")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Standing discount, e.g. 25 for NGOs")
    coupon = models.ForeignKey("coupons.Coupon", null=True, blank=True, on_delete=models.SET_NULL, related_name="subscriptions")
    coupon_payments_left = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Payments the coupon still applies to; blank: every payment")
    notes = models.TextField(blank=True, help_text="For MannaBooks staff only")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.workspace} on {self.plan}"

    @property
    def can_write(self) -> bool:
        return self.status not in (self.Status.READ_ONLY, self.Status.CANCELLED)
