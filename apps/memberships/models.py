from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.catalog import grants
from apps.core.models import WorkspaceModel


class Membership(WorkspaceModel):
    """One person's access to one workspace, through a role."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey("roles.Role", on_delete=models.PROTECT, related_name="memberships")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    approval_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
        help_text="Documents above this amount go to the module in-charge for approval.",
    )
    limited_department = models.ForeignKey(
        "departments.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="Sees only this department's documents and reports (and what they created). Blank: the whole business.",
    )

    class Meta:
        ordering = ["user__full_name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "user"], name="unique_membership_per_workspace")]

    def __str__(self):
        return f"{self.user} in {self.workspace} ({self.role})"

    @property
    def is_owner(self) -> bool:
        return self.role.slug == "owner"

    def has_perm(self, code: str) -> bool:
        return self.status == self.Status.ACTIVE and grants(self.role.permissions, code)
