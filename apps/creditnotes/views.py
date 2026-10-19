from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.sales_views import header_from
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import CreditNote
from .serializers import CreditNoteSerializer, CreditNoteVoidSerializer


class CreditNoteMixin(WorkspaceScopedMixin):
    queryset = CreditNote.objects.select_related("customer", "invoice").prefetch_related("lines__tax_rate", "lines__account")
    serializer_class = CreditNoteSerializer

    def note(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, note, code=status.HTTP_200_OK):
        self.kwargs["pk"] = note.pk
        return Response(CreditNoteSerializer(self.note(), context=self.get_serializer_context()).data, status=code)


class CreditNoteListCreateView(CreditNoteMixin, generics.ListCreateAPIView):
    """Credit notes are issued and posted when created."""

    permission_map = {"GET": "creditnotes.view", "POST": "creditnotes.create"}
    filterset_fields = {"status": ["exact"], "customer": ["exact"], "invoice": ["exact"], "issue_date": ["gte", "lte"]}
    search_fields = ["number", "customer__name", "reason"]
    ordering_fields = ["issue_date", "number", "total"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        note = services.create(
            request.workspace, header=header_from(d, request.workspace), rows=d.get("lines", []), reason=d["reason"],
            invoice=d.get("invoice"), return_stock=d.get("return_stock", True), user=request.user,
        )
        audit.record(request, "create", note)
        return self.respond(note, status.HTTP_201_CREATED)


class CreditNoteDetailView(CreditNoteMixin, generics.RetrieveAPIView):
    permission_map = {"GET": "creditnotes.view"}

    def get_object(self):
        return self.note()


class CreditNoteVoidView(CreditNoteMixin, generics.GenericAPIView):
    permission_map = {"POST": "creditnotes.void"}
    serializer_class = CreditNoteVoidSerializer

    @extend_schema(responses={200: CreditNoteSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = services.void(self.note(), serializer.validated_data["reason"], request.user)
        audit.record(request, "other", note, {"void": serializer.validated_data["reason"]})
        return self.respond(note)
