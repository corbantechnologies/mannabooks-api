"""
Abstract base models. `core` owns no tables: every concrete model lives in its own app.
"""
import uuid

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    """UUID primary key and timestamps for every MannaBooks table."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class WorkspaceModel(BaseModel):
    """A record that belongs to one workspace (tenant). Querysets are always filtered by it."""

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="+")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        abstract = True
