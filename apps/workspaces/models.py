from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class Workspace(BaseModel):
    """A business (tenant). Every workspace-owned row points here."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=60, unique=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_workspaces")
    legal_name = models.CharField(max_length=200, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)
    vat_registered = models.BooleanField(default=False)
    vat_number = models.CharField(max_length=30, blank=True)
    currency = models.CharField(max_length=3, default="KES")
    country = models.CharField(max_length=2, default="KE")
    timezone = models.CharField(max_length=50, default="Africa/Nairobi")
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    logo_url = models.URLField(blank=True)
    fiscal_year_start_month = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    modules = models.JSONField(default=list, blank=True, help_text="Switched-on modules (keys of APP_MODULES); empty means all")
    business_goal = models.CharField(max_length=20, blank=True, help_text="What the business chose to do first")
    is_active = models.BooleanField(default=True)
    # online shop
    store_enabled = models.BooleanField(default=False, help_text="Show the online shop at /shop/<slug>")
    store_intro = models.TextField(blank=True, help_text="A few words at the top of the shop")
    store_allow_pickup = models.BooleanField(default=True)
    store_allow_delivery = models.BooleanField(default=True)
    store_delivery_fee = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    store_pay_on_delivery = models.BooleanField(default=True, help_text="Let customers pay when they collect or receive the order")
    group = models.ForeignKey("companygroups.CompanyGroup", null=True, blank=True, on_delete=models.SET_NULL, related_name="workspaces",
                              help_text="The company group this business is reported with")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
