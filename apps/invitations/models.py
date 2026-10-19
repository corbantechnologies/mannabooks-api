import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import WorkspaceModel

INVITATION_DAYS = 7


def new_token() -> str:
    return secrets.token_urlsafe(32)


def default_expiry():
    return timezone.now() + timedelta(days=INVITATION_DAYS)


class Invitation(WorkspaceModel):
    """An email invitation to join a workspace with a role, optionally for an existing employee record."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"

    email = models.EmailField()
    role = models.ForeignKey("roles.Role", on_delete=models.CASCADE, related_name="invitations")
    employee = models.ForeignKey(
        "employees.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="invitations"
    )
    token = models.CharField(max_length=64, unique=True, default=new_token, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField(default=default_expiry)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} to {self.workspace}"

    @property
    def is_expired(self) -> bool:
        return self.status == self.Status.PENDING and self.expires_at < timezone.now()

    @property
    def link(self) -> str:
        return f"{settings.FRONTEND_URL}/invite/{self.token}"
