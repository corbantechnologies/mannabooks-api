from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import Membership
from .serializers import MembershipSerializer


def _active_owners(workspace):
    return Membership.objects.filter(workspace=workspace, role__slug="owner", status=Membership.Status.ACTIVE)


class MembershipQuerysetMixin(WorkspaceScopedMixin):
    module = "members"
    serializer_class = MembershipSerializer

    def workspace_queryset(self):
        return super().workspace_queryset().select_related("user", "role", "employee")


class MembershipListView(MembershipQuerysetMixin, generics.ListAPIView):
    """Members are added by invitation (see invitations), never created directly."""

    queryset = Membership.objects.all()
    filterset_fields = ["status", "role"]
    search_fields = ["user__full_name", "user__email"]


class MembershipDetailView(MembershipQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Membership.objects.all()
    http_method_names = ["get", "patch", "delete"]

    def perform_update(self, serializer):
        member = serializer.instance
        new_role = serializer.validated_data.get("role", member.role)
        new_status = serializer.validated_data.get("status", member.status)
        caller = self.request.membership
        if (new_role.slug == "owner") != member.is_owner and not caller.is_owner:
            raise BusinessRuleError("Only an Owner can give or take away the Owner role.")
        losing_owner = member.is_owner and (new_role.slug != "owner" or new_status != Membership.Status.ACTIVE)
        if losing_owner and _active_owners(self.request.workspace).count() <= 1:
            raise BusinessRuleError("A workspace needs at least one active Owner. Make someone else Owner first.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.is_owner:
            if not self.request.membership.is_owner:
                raise BusinessRuleError("Only an Owner can remove another Owner.")
            if _active_owners(self.request.workspace).count() <= 1:
                raise BusinessRuleError("A workspace needs at least one active Owner. Make someone else Owner first.")
        super().perform_destroy(instance)
