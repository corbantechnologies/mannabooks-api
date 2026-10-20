from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class SupportTicket(BaseModel):
    """
    A question, problem or complaint someone sends MannaBooks from inside the app. `messages` is the conversation:
    each entry {author_id, author_name, staff, body, at}. Staff can add private notes the customer doesn't see.
    """

    class Category(models.TextChoices):
        QUESTION = "question", "Question"
        PROBLEM = "problem", "Something isn't working"
        BILLING = "billing", "Billing and payments"
        COMPLAINT = "complaint", "Complaint"
        IDEA = "idea", "Idea or request"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        WAITING = "waiting", "Waiting for the customer"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    number = models.CharField(max_length=20, unique=True)
    workspace = models.ForeignKey("workspaces.Workspace", null=True, blank=True, on_delete=models.SET_NULL, related_name="support_tickets")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_tickets")
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.QUESTION)
    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    page = models.CharField(max_length=255, blank=True, help_text="The page they were on")
    messages = models.JSONField(default=list)
    last_reply_by_staff = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.number}: {self.subject}"
