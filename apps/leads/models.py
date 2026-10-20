from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class Lead(WorkspaceModel):
    """Someone who might buy: a walk-in, a call, a referral. Qualified leads become customers (and usually a deal)."""

    class Source(models.TextChoices):
        WALK_IN = "walk_in", "Walk-in"
        CALL = "call", "Phone call"
        REFERRAL = "referral", "Referral"
        WEBSITE = "website", "Website"
        SOCIAL = "social", "Social media"
        EVENT = "event", "Event or exhibition"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUALIFIED = "qualified", "Qualified"
        CONVERTED = "converted", "Converted"
        LOST = "lost", "Lost"

    number = models.CharField(max_length=30)
    name = models.CharField(max_length=150, help_text="The person")
    company = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.OTHER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    interest = models.CharField(max_length=255, blank=True, help_text="What they want")
    estimated_value = models.DecimalField(**MONEY_FIELD, default=0)
    assigned_to = models.ForeignKey("memberships.Membership", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads",
                                 help_text="Set when the lead is converted")
    lost_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["workspace", "number"], name="unique_lead_number")]

    def __str__(self):
        return f"{self.name} ({self.company})" if self.company else self.name
