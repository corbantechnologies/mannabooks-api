from django.db import models

from apps.core.models import BaseModel, WorkspaceModel


class Product(WorkspaceModel):
    """Something the business sells: goods or a service. Stock tracking arrives with Inventory."""

    class Kind(models.TextChoices):
        GOODS = "goods", "Goods"
        SERVICE = "service", "Service"

    code = models.CharField(max_length=40, blank=True, help_text="SKU or item code")
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.GOODS)
    description = models.TextField(blank=True)
    category = models.ForeignKey("productcategories.ProductCategory", null=True, blank=True, on_delete=models.PROTECT, related_name="products")
    unit = models.CharField(max_length=20, default="pcs", help_text="Abbreviation of a unit, e.g. pcs or kg")
    sale_price = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    cost_price = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    tax_rate = models.ForeignKey("taxrates.TaxRate", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    income_account = models.ForeignKey(
        "ledgeraccounts.LedgerAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Blank: Sales for goods, Service income for services",
    )
    track_inventory = models.BooleanField(default=False, help_text="Keep stock levels and cost of sales for this product")
    online = models.BooleanField(default=False, db_default=False, help_text="Show it in the online shop")
    image_url = models.URLField(blank=True, db_default="", help_text="A picture for the online shop")
    made_to_order = models.BooleanField(
        default=False, help_text="Made when sold (a meal, a mixed drink): selling it takes its recipe's ingredients out of stock",
    )
    reorder_level = models.DecimalField(max_digits=14, decimal_places=3, default=0, help_text="Warn when stock falls to this")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "code"], condition=~models.Q(code=""), name="unique_product_code")
        ]

    def __str__(self):
        return self.name


class ProductUnit(BaseModel):
    """Another unit the product is bought or sold in, e.g. a carton of 24 pieces. Stock stays in the product's own unit."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="units")
    unit = models.CharField(max_length=20, help_text="Abbreviation of a unit, e.g. ctn")
    factor = models.DecimalField(max_digits=14, decimal_places=4, help_text="How many of the product's own unit one of these holds")
    sale_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True,
                                     help_text="Price of one of these; blank: the product's price times the factor")

    class Meta:
        ordering = ["factor"]
        constraints = [models.UniqueConstraint(fields=["product", "unit"], name="one_conversion_per_unit")]

    def __str__(self):
        return f"1 {self.unit} = {self.factor.normalize():f} {self.product.unit}"
