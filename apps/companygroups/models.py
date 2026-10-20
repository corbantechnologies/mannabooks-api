from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class CompanyGroup(BaseModel):
    """
    Several businesses (workspaces) with one owner, reported on together: consolidated profit and loss and balance
    sheet, with what they sell to and lend each other taken out. A workspace belongs to at most one group.
    """

    name = models.CharField(max_length=150)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="company_groups")
    currency = models.CharField(max_length=3, default="KES", help_text="Every company in the group keeps its books in this currency")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
