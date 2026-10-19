from django.db import models

from apps.core.models import BaseModel, WorkspaceModel


class PriceList(WorkspaceModel):
    """
    Special prices for a group of customers (wholesale, staff, a contract). A product's price is its
    item on the list if there is one, otherwise its normal price adjusted by `adjust_percent`.
    """

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    adjust_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0,
                                         help_text="For products not listed: -10 is 10% below the normal price")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_price_list_name")]

    def __str__(self):
        return self.name


class PriceListItem(BaseModel):
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="+")
    price = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        ordering = ["product__name"]
        constraints = [models.UniqueConstraint(fields=["price_list", "product"], name="one_price_per_product")]
