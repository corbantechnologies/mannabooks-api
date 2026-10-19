from django.db import models

from apps.core.models import WorkspaceModel


class LoyaltyProgram(WorkspaceModel):
    """
    How customers earn and spend points. Points are earned on sales net of VAT (cash sales and issued
    invoices) and redeemed at the till as a discount on the sale.
    """

    name = models.CharField(max_length=80, default="Rewards")
    is_active = models.BooleanField(default=False)
    spend_per_point = models.DecimalField(max_digits=12, decimal_places=2, default=100, help_text="KES spent (before VAT) to earn 1 point")
    point_value = models.DecimalField(max_digits=10, decimal_places=2, default=1, help_text="KES discount for 1 point redeemed")
    min_redeem_points = models.PositiveIntegerField(default=100)
    max_redeem_percent = models.PositiveSmallIntegerField(default=50, help_text="Most of a sale that points can pay for")
    expiry_months = models.PositiveSmallIntegerField(default=12, help_text="Points expire this many months after they are earned; 0 never")
    earn_on_invoices = models.BooleanField(default=True, help_text="Also earn on invoices, not only cash sales")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_loyalty_program_per_workspace")]

    def __str__(self):
        return self.name
