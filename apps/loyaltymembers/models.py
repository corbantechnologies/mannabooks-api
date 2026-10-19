from django.db import models

from apps.core.models import WorkspaceModel


class LoyaltyMember(WorkspaceModel):
    """A customer enrolled in the loyalty programme, with their card number and points."""

    customer = models.OneToOneField("customers.Customer", on_delete=models.PROTECT, related_name="loyalty")
    card_number = models.CharField(max_length=30)
    tier = models.ForeignKey("loyaltytiers.LoyaltyTier", null=True, blank=True, on_delete=models.SET_NULL, related_name="members")
    points_balance = models.IntegerField(default=0)
    lifetime_points = models.PositiveIntegerField(default=0)
    qualifying_points = models.PositiveIntegerField(default=0, help_text="Earned in the last 12 months; sets the tier")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-points_balance"]
        constraints = [models.UniqueConstraint(fields=["workspace", "card_number"], name="unique_loyalty_card")]

    def __str__(self):
        return f"{self.card_number} {self.customer}"
