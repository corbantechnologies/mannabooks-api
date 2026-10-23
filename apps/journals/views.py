from django.db.models import Sum
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import JournalEntry
from .serializers import JournalEntrySerializer, JournalListSerializer, ReverseSerializer


def _line_inputs(rows):
    return [
        services.LineInput(account=r["account"], debit=r.get("debit") or 0, credit=r.get("credit") or 0,
                           description=r.get("description", ""), branch=r.get("branch"), department=r.get("department"),
                           cost_center=r.get("cost_center"), project=r.get("project"))
        for r in rows
    ]


class JournalMixin(WorkspaceScopedMixin):
    queryset = JournalEntry.objects.all()

    def check_permissions(self, request):
        super().check_permissions(request)
        from apps.core.scoping import deny_if_limited

        deny_if_limited(request, "The journal")

    def entry(self) -> JournalEntry:
        return workspace_object(
            JournalEntry.objects.select_related("posted_by", "reversal_of").prefetch_related("lines__account"),
            self.request, pk=self.kwargs["pk"],
        )


class JournalListCreateView(JournalMixin, generics.ListCreateAPIView):
    """Journal entries. Creating one makes a manual draft; post it separately."""

    permission_map = {"GET": "journals.view", "POST": "journals.create"}
    filterset_fields = {"status": ["exact"], "source": ["exact"], "entry_date": ["gte", "lte"]}
    search_fields = ["number", "description", "reference"]
    ordering_fields = ["entry_date", "number", "created_at"]

    def get_serializer_class(self):
        return JournalListSerializer if self.request.method == "GET" else JournalEntrySerializer

    def workspace_queryset(self):
        return super().workspace_queryset().annotate(total=Sum("lines__debit")).order_by("-entry_date", "-created_at")

    def perform_create(self, serializer):
        data = serializer.validated_data
        entry = services.create_draft(
            self.request.workspace, entry_date=data["entry_date"], description=data["description"],
            reference=data.get("reference", ""), lines=_line_inputs(data["lines"]), user=self.request.user,
        )
        audit.record(self.request, "create", entry)
        serializer.instance = entry


class JournalDetailView(JournalMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = JournalEntrySerializer
    permission_map = {"GET": "journals.view", "PATCH": "journals.create", "DELETE": "journals.create"}
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.entry()

    def perform_update(self, serializer):
        data = dict(serializer.validated_data)
        rows = data.pop("lines", None)
        before = audit.snapshot(serializer.instance)
        entry = services.update_draft(serializer.instance, lines=_line_inputs(rows) if rows is not None else None, **data)
        audit.record(self.request, "update", entry, audit.diff(before, audit.snapshot(entry)))
        serializer.instance = JournalEntry.objects.prefetch_related("lines__account").get(pk=entry.pk)

    def perform_destroy(self, instance):
        if instance.status != JournalEntry.Status.DRAFT:
            raise BusinessRuleError("Posted entries can't be deleted. Reverse them instead.")
        super().perform_destroy(instance)


class JournalPostView(JournalMixin, generics.GenericAPIView):
    serializer_class = JournalEntrySerializer
    permission_map = {"POST": "journals.post"}

    @extend_schema(request=None, responses={200: JournalEntrySerializer})
    def post(self, request, workspace, pk):
        entry = services.post_draft(self.entry(), user=request.user)
        audit.record(request, "other", entry, {"posted": entry.number})
        return Response(self.get_serializer(self.entry()).data)


class JournalReverseView(JournalMixin, generics.GenericAPIView):
    serializer_class = ReverseSerializer
    permission_map = {"POST": "journals.reverse"}

    @extend_schema(responses={201: JournalEntrySerializer})
    def post(self, request, workspace, pk):
        entry = self.entry()
        if entry.source != "manual":
            raise BusinessRuleError(f"This entry comes from {entry.source.replace('_', ' ')}. Change it there instead.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reversal = services.reverse_entry(
            entry, entry_date=serializer.validated_data["entry_date"], user=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        audit.record(request, "other", entry, {"reversed_by": reversal.number})
        self.kwargs["pk"] = reversal.pk
        return Response(JournalEntrySerializer(self.entry(), context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)
