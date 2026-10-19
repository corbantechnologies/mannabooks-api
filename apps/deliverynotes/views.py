from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import DeliveryNote
from .serializers import DeliveryActionSerializer, DeliveryNoteSerializer

HEADER = ("customer", "invoice", "delivery_date", "delivery_address", "contact_person", "contact_phone", "vehicle", "driver", "notes")


class DeliveryNoteMixin(WorkspaceScopedMixin):
    module = "deliverynotes"
    queryset = DeliveryNote.objects.select_related("customer", "invoice").prefetch_related("lines")
    serializer_class = DeliveryNoteSerializer

    def note(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, note, code=status.HTTP_200_OK):
        self.kwargs["pk"] = note.pk
        return Response(DeliveryNoteSerializer(self.note(), context=self.get_serializer_context()).data, status=code)


class DeliveryNoteListCreateView(DeliveryNoteMixin, generics.ListCreateAPIView):
    filterset_fields = {"status": ["exact"], "customer": ["exact"], "invoice": ["exact"], "delivery_date": ["gte", "lte"]}
    search_fields = ["number", "customer__name", "vehicle", "driver"]
    ordering_fields = ["delivery_date", "number"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        note = services.save(request.workspace, data={k: d[k] for k in HEADER if k in d}, rows=d.get("lines"), user=request.user)
        audit.record(request, "create", note)
        return self.respond(note, status.HTTP_201_CREATED)


class DeliveryNoteDetailView(DeliveryNoteMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.note()

    def update(self, request, *args, **kwargs):
        note = self.note()
        serializer = self.get_serializer(note, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        note = services.save(request.workspace, data={k: d[k] for k in HEADER if k in d}, rows=d.get("lines"), user=request.user, note=note)
        audit.record(request, "update", note)
        return self.respond(note)

    def perform_destroy(self, instance):
        if instance.status != DeliveryNote.Status.DRAFT:
            raise BusinessRuleError("Only drafts can be deleted. Void it instead.")
        super().perform_destroy(instance)


class DeliveryNoteStatusView(DeliveryNoteMixin, generics.GenericAPIView):
    serializer_class = DeliveryActionSerializer

    @extend_schema(responses={200: DeliveryNoteSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = services.change_status(self.note(), serializer.validated_data["action"], serializer.validated_data.get("received_by", ""))
        audit.record(request, "other", note, {"status": note.status})
        return self.respond(note)
