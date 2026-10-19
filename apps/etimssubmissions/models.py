from django.db import models

from apps.core.models import WorkspaceModel


class EtimsSubmission(WorkspaceModel):
    """One attempt to have KRA eTIMS sign a document, with what was sent and what came back."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SIGNED = "signed", "Signed"
        FAILED = "failed", "Failed"

    document_type = models.CharField(max_length=20)  # invoice, receipt, credit_note
    document_id = models.UUIDField()
    document_number = models.CharField(max_length=30)
    kra_invoice_number = models.PositiveIntegerField(help_text="The device's sequence number sent to KRA")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    payload = models.JSONField(default=dict)
    response = models.JSONField(default=dict, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "document_type", "document_id"])]

    def __str__(self):
        return f"{self.document_number} ({self.status})"
