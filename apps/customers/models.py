from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class Customer(WorkspaceModel):
    """Someone the business sells to. Walk-in cash sales need no customer."""

    class Kind(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        COMPANY = "company", "Company"

    number = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.COMPANY)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=3, blank=True, help_text="Blank: the base currency")
    payment_terms_days = models.PositiveSmallIntegerField(default=0, help_text="Days to pay; 0 is due on receipt")
    price_list = models.ForeignKey("pricelists.PriceList", null=True, blank=True, on_delete=models.PROTECT, related_name="customers",
                                   help_text="Blank: normal prices")
    credit_limit = models.DecimalField(**MONEY_FIELD, default=0, help_text="0: no limit")
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "number"], name="unique_customer_number")]

    def __str__(self):
        return self.name
