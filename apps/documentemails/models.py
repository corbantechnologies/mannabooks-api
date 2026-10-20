from django.db import models

from apps.core.models import WorkspaceModel


class DocumentEmail(WorkspaceModel):
    """One email of a document to a customer or supplier. `created_by` sent it."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Not sent"

    document_type = models.CharField(max_length=30)
    object_id = models.UUIDField()
    document_number = models.CharField(max_length=60)
    to = models.CharField(max_length=500, help_text="Comma-separated addresses")
    cc = models.CharField(max_length=500, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField(blank=True, help_text="The sender's own note, above the document summary")
    link = models.URLField(max_length=300, blank=True, help_text="The private view-and-pay link, for invoices")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    error = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "document_type", "object_id"])]

    def __str__(self):
        return f"{self.document_number} to {self.to}"
