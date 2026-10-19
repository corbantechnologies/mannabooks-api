from django.db import models

from apps.core.models import WorkspaceModel


class Role(WorkspaceModel):
    """A named set of permissions (`module.action`) that members of a workspace hold."""

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80)
    description = models.CharField(max_length=255, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    is_preset = models.BooleanField(default=False, help_text="Created with the workspace; cannot be deleted.")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "slug"], name="unique_role_slug_per_workspace")]

    def __str__(self):
        return self.name
