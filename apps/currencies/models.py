from django.db import models

from apps.core.models import WorkspaceModel


class Currency(WorkspaceModel):
    """A currency the workspace deals in. Exactly one is the base currency the books are kept in."""

    code = models.CharField(max_length=3)
    name = models.CharField(max_length=60)
    symbol = models.CharField(max_length=8, blank=True)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    is_base = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_base", "code"]
        verbose_name_plural = "currencies"
        constraints = [models.UniqueConstraint(fields=["workspace", "code"], name="unique_currency_per_workspace")]

    def __str__(self):
        return self.code
