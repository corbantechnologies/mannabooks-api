"""
Workspace tenancy for DRF generic views.

Every workspace-scoped URL carries the workspace slug (`/api/v1/w/<workspace>/...`). The permission
class resolves it, checks the caller's active membership and the permission the view requires, and
stores both on the request. `WorkspaceScopedMixin` then filters querysets and stamps new rows, so a
view cannot forget to scope its data.
"""
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated

from apps.auditlogs import services as audit


def resolve_membership(request, slug: str):
    from apps.memberships.models import Membership
    from apps.workspaces.models import Workspace

    workspace = Workspace.objects.filter(slug=slug, is_active=True).first()
    if workspace is None:
        raise NotFound("Workspace not found.")
    membership = (
        Membership.objects.select_related("role")
        .filter(workspace=workspace, user=request.user, status=Membership.Status.ACTIVE)
        .first()
    )
    if membership is None:
        # Same answer as a missing workspace, so workspace names cannot be probed.
        raise NotFound("Workspace not found.")
    return workspace, membership


class WorkspacePermission(BasePermission):
    """Requires an active membership in the URL's workspace and the view's permission code."""

    def has_permission(self, request, view):
        slug = view.kwargs.get("workspace")
        if not slug:
            return False
        workspace, membership = resolve_membership(request, slug)
        request.workspace = workspace
        request.membership = membership
        code = view.required_permission(request) if hasattr(view, "required_permission") else None
        if code and not membership.has_perm(code):
            raise PermissionDenied(f"Your role ({membership.role.name}) does not allow this ({code}).")
        if not getattr(view, "subscription_exempt", False):  # billing, support and the context stay usable
            if workspace.blocked_at:
                raise PermissionDenied(f"MannaBooks has blocked {workspace.name}: {workspace.blocked_reason or 'contact MannaBooks'}. "
                                       "Use Help and feedback to reach us.")
            if request.method not in SAFE_METHODS:
                from apps.subscriptions.services import check_write

                check_write(workspace, code)
        return True


class WorkspaceScopedMixin:
    """
    Mixin for generic views on a `WorkspaceModel`.

    Set `module` (e.g. "branches"): reads need `<module>.view`, writes `<module>.manage`.
    Override `permission_map = {"POST": "branches.manage", ...}` for anything finer.
    """

    permission_classes = [IsAuthenticated, WorkspacePermission]
    module: str = ""
    permission_map: dict[str, str] = {}

    def required_permission(self, request) -> str | None:
        if request.method in self.permission_map:
            return self.permission_map[request.method]
        if not self.module:
            return None
        return f"{self.module}.view" if request.method in SAFE_METHODS else f"{self.module}.manage"

    @property
    def workspace(self):
        return self.request.workspace

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation: no request workspace
            return self.queryset.none()
        from .scoping import scope_queryset

        return scope_queryset(self.workspace_queryset(), self.request)  # someone limited to a department sees its rows only

    def workspace_queryset(self):
        """Rows of this view's model in the request's workspace. Override to add joins or filters."""
        return self.queryset.filter(workspace=self.request.workspace)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["workspace"] = getattr(self.request, "workspace", None)
        return context

    def perform_create(self, serializer):
        instance = serializer.save(workspace=self.request.workspace, created_by=self.request.user)
        audit.record(self.request, "create", instance)

    def perform_update(self, serializer):
        before = audit.snapshot(serializer.instance)
        instance = serializer.save()
        audit.record(self.request, "update", instance, audit.diff(before, audit.snapshot(instance)))

    def perform_destroy(self, instance):
        audit.record(self.request, "delete", instance)
        instance.delete()


def workspace_object(model, request, **lookup):
    """Fetch a row of `model` inside the request's workspace, and inside the caller's department if they are limited to one (404 otherwise)."""
    from django.db.models import QuerySet

    from .scoping import scope_queryset

    qs = model if isinstance(model, QuerySet) else model.objects.all()  # a model, or a queryset with its joins
    return get_object_or_404(scope_queryset(qs.filter(workspace=request.workspace), request), **lookup)
