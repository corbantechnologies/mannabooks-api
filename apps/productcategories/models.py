from django.db import models

from apps.core.models import WorkspaceModel


class ProductCategory(WorkspaceModel):
    """Groups products (e.g. Building materials > Cement) for lists, reports and the till."""

    name = models.CharField(max_length=120)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    description = models.TextField(blank=True)
    tax_rate = models.ForeignKey("taxrates.TaxRate", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                 help_text="VAT rate for new products in this category; blank: the parent's, then the workspace default")
    income_account = models.ForeignKey("ledgeraccounts.LedgerAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                       help_text="Income account for new products; blank: the parent's, then Sales")
    markup_percent = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True,
                                         help_text="Suggests a selling price from the cost: cost x (1 + markup)")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "product categories"
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_product_category_name")]

    def __str__(self):
        return self.name

    def setting(self, field: str):
        """This category's value for a default, else the nearest parent's."""
        category, seen = self, set()
        while category is not None and category.pk not in seen:
            seen.add(category.pk)
            value = getattr(category, field)
            if value is not None:
                return value
            category = category.parent
        return None
