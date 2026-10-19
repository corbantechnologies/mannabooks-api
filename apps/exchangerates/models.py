from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import RATE_FIELD


class ExchangeRate(WorkspaceModel):
    """How much one unit of a foreign currency is worth in the base currency on a date."""

    currency = models.ForeignKey("currencies.Currency", on_delete=models.CASCADE, related_name="rates")
    rate_date = models.DateField()
    rate = models.DecimalField(**RATE_FIELD, help_text="1 unit of the currency in the base currency")
    source = models.CharField(max_length=40, default="manual")

    class Meta:
        ordering = ["-rate_date"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "currency", "rate_date"], name="unique_rate_per_currency_day")
        ]

    def __str__(self):
        return f"{self.currency.code} {self.rate} on {self.rate_date}"
