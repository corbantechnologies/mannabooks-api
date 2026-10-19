from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import ApprovalRule
from .serializers import ApprovalRuleSerializer


class RuleMixin(WorkspaceScopedMixin):
    module = "approvals"
    queryset = ApprovalRule.objects.all()
    serializer_class = ApprovalRuleSerializer


class ApprovalRuleListCreateView(RuleMixin, generics.ListCreateAPIView):
    filterset_fields = ["document_type", "is_active"]
    pagination_class = None


class ApprovalRuleDetailView(RuleMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]
