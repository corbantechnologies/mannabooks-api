from django.db import transaction
from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import Branch
from .serializers import BranchSerializer


class BranchMixin(WorkspaceScopedMixin):
    module = "branches"
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer

    @transaction.atomic
    def _keep_one_default(self, branch):
        if branch.is_default:
            Branch.objects.filter(workspace=branch.workspace, is_default=True).exclude(pk=branch.pk).update(is_default=False)


class BranchListCreateView(BranchMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active"]
    search_fields = ["name", "code"]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._keep_one_default(serializer.instance)


class BranchDetailView(BranchMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_update(self, serializer):
        if serializer.instance.is_default and serializer.validated_data.get("is_default") is False:
            raise BusinessRuleError("Pick another branch as the default instead of switching this one off.")
        super().perform_update(serializer)
        self._keep_one_default(serializer.instance)

    def perform_destroy(self, instance):
        if instance.is_default:
            raise BusinessRuleError("The default branch can't be deleted.")
        super().perform_destroy(instance)
