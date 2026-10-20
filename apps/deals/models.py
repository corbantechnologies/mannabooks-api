from decimal import Decimal

from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class Deal(WorkspaceModel):
    """A sale being worked on, moving through the pipeline from first contact to won or lost."""

    class Stage(models.TextChoices):
        PROSPECT = "prospect", "Prospect"
        QUALIFIED = "qualified", "Qualified"
        PROPOSAL = "proposal", "Quote sent"
        NEGOTIATION = "negotiation", "Negotiation"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    # How likely each open stage is to close, for the weighted pipeline. A deal can override it.
    STAGE_PROBABILITY = {"prospect": 10, "qualified": 25, "proposal": 50, "negotiation": 75, "won": 100, "lost": 0}

    number = models.CharField(max_length=30)
    title = models.CharField(max_length=200)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="deals")
    lead = models.ForeignKey("leads.Lead", null=True, blank=True, on_delete=models.SET_NULL, related_name="deals")
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.PROSPECT)
    value = models.DecimalField(**MONEY_FIELD, default=0, help_text="Expected value before VAT")
    probability = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Percent; blank: the stage's usual chance")
    expected_close_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey("memberships.Membership", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    quotation = models.ForeignKey("quotations.Quotation", null=True, blank=True, on_delete=models.SET_NULL, related_name="deals")
    closed_at = models.DateField(null=True, blank=True)
    lost_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["workspace", "number"], name="unique_deal_number")]

    def __str__(self):
        return self.title

    @property
    def chance(self) -> int:
        return self.probability if self.probability is not None else self.STAGE_PROBABILITY.get(self.stage, 0)

    @property
    def weighted_value(self) -> Decimal:
        return (self.value * self.chance / 100).quantize(Decimal("0.01"))
