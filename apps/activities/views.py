from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import Activity
from .serializers import ActivitySerializer


class ActivityMixin(WorkspaceScopedMixin):
    module = "crm"
    queryset = Activity.objects.select_related("assigned_to__user", "lead", "deal", "customer")
    serializer_class = ActivitySerializer


@extend_schema_view(get=extend_schema(parameters=[
    OpenApiParameter("mine", OpenApiTypes.BOOL, description="Only activities assigned to you"),
    OpenApiParameter("open", OpenApiTypes.BOOL, description="true: not done yet; false: done"),
    OpenApiParameter("overdue", OpenApiTypes.BOOL, description="Open and past their due time"),
]))
class ActivityListCreateView(ActivityMixin, generics.ListCreateAPIView):
    filterset_fields = ["kind", "lead", "deal", "customer", "assigned_to"]
    search_fields = ["subject", "notes"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("mine") == "true":
            qs = qs.filter(assigned_to=self.request.membership)
        if p.get("open") in ("true", "false"):
            qs = qs.filter(done_at__isnull=p["open"] == "true")
        if p.get("overdue") == "true":
            qs = qs.filter(done_at__isnull=True, due_at__lt=timezone.now())
        return qs

    def perform_create(self, serializer):
        serializer.validated_data.setdefault("assigned_to", self.request.membership)
        super().perform_create(serializer)


class ActivityDetailView(ActivityMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]
