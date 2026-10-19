from django.db import models

from apps.core.models import WorkspaceModel


class LoyaltyTransaction(WorkspaceModel):
    """
    One movement of a member's points. Earned points keep `remaining` (what is left unspent) and
    `expires_on`, so redemptions use the oldest points first and expiry only takes what is left.
    """

    class Kind(models.TextChoices):
        EARN = "earn", "Earned"
        REDEEM = "redeem", "Redeemed"
        EXPIRE = "expire", "Expired"
        ADJUST = "adjust", "Adjusted"
        REVERSE = "reverse", "Reversed"

    member = models.ForeignKey("loyaltymembers.LoyaltyMember", on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    points = models.IntegerField(help_text="Positive adds, negative removes")
    remaining = models.PositiveIntegerField(default=0)
    expires_on = models.DateField(null=True, blank=True)
    document_type = models.CharField(max_length=20, blank=True)
    document_id = models.UUIDField(null=True, blank=True)
    document_number = models.CharField(max_length=30, blank=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["member", "kind"]), models.Index(fields=["document_id"])]
