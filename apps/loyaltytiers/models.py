from django.db import models

from apps.core.models import WorkspaceModel


class LoyaltyTier(WorkspaceModel):
    """A level members reach by points earned in the last 12 months (e.g. Silver, Gold). Higher tiers earn faster."""

    name = models.CharField(max_length=60)
    min_points = models.PositiveIntegerField(default=0, help_text="Points earned in the last 12 months to qualify")
    multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1, help_text="1.5 earns 50% more points")
    perks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["min_points"]
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_loyalty_tier_name")]

    def __str__(self):
        return self.name
