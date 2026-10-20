from django.db import models

from apps.core.models import WorkspaceModel


class Activity(WorkspaceModel):
    """A call, meeting, email, task or note about a lead, deal or customer. Open tasks show on the person's list until done."""

    class Kind(models.TextChoices):
        CALL = "call", "Call"
        MEETING = "meeting", "Meeting"
        EMAIL = "email", "Email"
        TASK = "task", "Task"
        NOTE = "note", "Note"

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TASK)
    subject = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey("memberships.Membership", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    lead = models.ForeignKey("leads.Lead", null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    deal = models.ForeignKey("deals.Deal", null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.CASCADE, related_name="activities")

    class Meta:
        ordering = ["done_at", "due_at", "-created_at"]
        verbose_name_plural = "activities"

    def __str__(self):
        return self.subject
