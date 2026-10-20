from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class PlatformAction(BaseModel):
    """What MannaBooks staff did in the platform admin: blocking a business, changing a plan, recording a payment."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=40)
    target_type = models.CharField(max_length=40)
    target_id = models.CharField(max_length=64)
    target_label = models.CharField(max_length=200, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.target_label}"
