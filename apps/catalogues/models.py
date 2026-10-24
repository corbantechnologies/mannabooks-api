import secrets

from django.conf import settings
from django.db import models

from apps.core.models import WorkspaceModel


def new_token() -> str:
    return secrets.token_urlsafe(18)


class Catalogue(WorkspaceModel):
    """
    A list of products the business shares by private link. The client picks what they want and quantities, and
    MannaBooks writes the quotation from their picks: sent to them at once, or kept as a draft for the team to review.
    """

    class QuoteMode(models.TextChoices):
        AUTO = "auto", "Send the quote at once"
        REVIEW = "review", "Review before sending"

    name = models.CharField(max_length=150, help_text="For example: Laptops for Acme Ltd")
    intro = models.TextField(blank=True, help_text="A few words at the top of the catalogue")
    token = models.CharField(max_length=40, unique=True, default=new_token, editable=False)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.CASCADE, related_name="catalogues",
                                 help_text="Blank: anyone with the link")
    price_list = models.ForeignKey("pricelists.PriceList", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                   help_text="Blank: the customer's price list, else normal prices")
    categories = models.ManyToManyField("productcategories.ProductCategory", blank=True, related_name="+",
                                        help_text="Everything in these categories (and their sub-categories), now and later")
    products = models.ManyToManyField("products.Product", blank=True, related_name="+", help_text="Picked by hand")
    excluded_products = models.ManyToManyField("products.Product", blank=True, related_name="+",
                                               help_text="Left out even though their category is in")
    quote_mode = models.CharField(max_length=10, choices=QuoteMode.choices, default=QuoteMode.AUTO)
    show_prices = models.BooleanField(default=True, help_text="Off: prices on request, and every quote is reviewed first")
    show_stock = models.BooleanField(default=False, help_text="Show In stock or Out of stock (never the numbers)")
    expires_on = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    view_count = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def url(self) -> str:
        return f"{settings.FRONTEND_URL}/c/{self.token}"

    @property
    def reviews_first(self) -> bool:
        return self.quote_mode == self.QuoteMode.REVIEW or not self.show_prices
