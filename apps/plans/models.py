from django.db import models

from apps.core.models import BaseModel
from apps.core.money import MONEY_FIELD


class Plan(BaseModel):
    """
    A MannaBooks price plan: what a business pays and what it gets (modules, users, documents a month).
    Platform staff edit plans in the admin; changing a price applies from each business's next payment.
    """

    key = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=255, blank=True)
    price_monthly = models.DecimalField(**MONEY_FIELD, default=0, help_text="KES a month, VAT included")
    price_yearly = models.DecimalField(**MONEY_FIELD, default=0, help_text="KES for a year paid at once (usually 10 months' price)")
    modules = models.JSONField(default=list, help_text="APP_MODULES keys this plan includes")
    features = models.JSONField(default=list, blank=True, help_text="Extra features, e.g. company_groups")
    max_users = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Team members, not counting accountants and self-service staff; blank: no limit")
    max_documents_month = models.PositiveIntegerField(null=True, blank=True, help_text="Invoices, cash sales and quotations a month; blank: no limit")
    payroll_per_employee = models.DecimalField(**MONEY_FIELD, default=0, help_text="Payroll add-on, KES per employee a month")
    payroll_minimum = models.DecimalField(**MONEY_FIELD, default=0, help_text="Lowest payroll add-on a month, once payroll is used")
    is_free = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True, help_text="Shown on the pricing page and to businesses choosing a plan")
    is_active = models.BooleanField(default=True)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort", "price_monthly"]

    def __str__(self):
        return self.name

    def includes(self, module: str) -> bool:
        return module in (self.modules or [])
