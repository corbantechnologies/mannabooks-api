from django.conf import settings
from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class ApprovalRequest(WorkspaceModel):
    """
    One document going through an approval chain. `levels` is a copy of the rule's levels when it was
    sent, so changing the rule doesn't change requests already on their way. `created_by` is the requester.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Withdrawn"

    document_type = models.CharField(max_length=30)
    object_id = models.UUIDField()
    document_number = models.CharField(max_length=80)
    summary = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(**MONEY_FIELD, default=0)
    rule = models.ForeignKey("approvalrules.ApprovalRule", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    levels = models.JSONField(default=list)
    current_level = models.PositiveSmallIntegerField(default=0, help_text="Index into levels")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    used = models.BooleanField(default=False, help_text="Set when the approved document has been approved")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "document_type", "object_id"]), models.Index(fields=["workspace", "status"])]

    def __str__(self):
        return f"{self.document_number} ({self.get_status_display()})"


class ApprovalStep(BaseModel):
    """One person's decision at one level."""

    request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name="steps")
    level = models.PositiveSmallIntegerField()
    decision = models.CharField(max_length=10, choices=[("approved", "Approved"), ("rejected", "Rejected")])
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    comment = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at"]
