from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class DepreciationEntry(WorkspaceModel):
    """One month's depreciation of one asset. A run posts all of its month's entries as one journal."""

    asset = models.ForeignKey("fixedassets.FixedAsset", on_delete=models.CASCADE, related_name="depreciation_entries")
    month_end = models.DateField(help_text="The month depreciated")
    run_month = models.DateField(help_text="The run (month end) that posted it; catch-up months join the run that charged them")
    amount = models.DecimalField(**MONEY_FIELD)
    prior_depreciated_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-month_end"]
        constraints = [models.UniqueConstraint(fields=["asset", "month_end"], name="one_depreciation_per_asset_month")]
