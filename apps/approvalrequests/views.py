from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import ApprovalRequest
from .registry import DOCS
from .serializers import ApprovalRequestSerializer, ApprovalStatusSerializer, DecideSerializer, SubmitSerializer


class RequestMixin(WorkspaceScopedMixin):
    """Everyone sees requests waiting on them and their own; approvals.view sees all."""

    permission_map = {"GET": None, "POST": None}
    queryset = ApprovalRequest.objects.select_related("created_by", "workspace").prefetch_related("steps__decided_by")
    serializer_class = ApprovalRequestSerializer

    def respond(self, req, code=status.HTTP_200_OK):
        return Response(ApprovalRequestSerializer(self.queryset.get(pk=req.pk), context=self.get_serializer_context()).data, status=code)


class ApprovalRequestListCreateView(RequestMixin, generics.ListCreateAPIView):
    """
    GET: `?box=waiting` (waiting on me, the default), `mine` (I asked), or `all` (approvals.view).
    POST: send a document for approval.
    """

    filterset_fields = ["status", "document_type"]
    search_fields = ["document_number", "summary"]

    def get_serializer_class(self):
        return SubmitSerializer if self.request.method == "POST" else ApprovalRequestSerializer

    @extend_schema(parameters=[OpenApiParameter("box", OpenApiTypes.STR, enum=["waiting", "mine", "all"])])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def workspace_queryset(self):
        qs = super().workspace_queryset()
        box = self.request.query_params.get("box", "waiting")
        user = self.request.user
        if box == "mine":
            return qs.filter(created_by=user)
        if box == "all":
            if not self.request.membership.has_perm("approvals.view"):
                raise PermissionDenied("Your role does not allow this (approvals.view).")
            return qs
        ids = [r.pk for r in qs.filter(status=ApprovalRequest.Status.PENDING) if services.can_decide(r, user)]
        return qs.filter(pk__in=ids)

    @extend_schema(request=SubmitSerializer, responses={201: ApprovalRequestSerializer})
    def post(self, request, *args, **kwargs):
        serializer = SubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        spec = DOCS[d["document_type"]]
        if not request.membership.has_perm(spec.submit_perm):
            raise PermissionDenied(f"Your role does not allow this ({spec.submit_perm}).")
        obj = spec.get(request.workspace, d["object_id"])
        if obj is None:
            raise NotFound("Document not found.")
        req = services.submit(request.workspace, d["document_type"], obj, request.user)
        if req is None:
            raise BusinessRuleError("No approval rule covers this. Someone with approval rights can approve it directly.")
        audit.record(request, "other", req, {"submitted": req.document_number})
        return self.respond(req, status.HTTP_201_CREATED)


class ApprovalRequestDetailView(RequestMixin, generics.RetrieveAPIView):
    pass


class ApprovalDecideView(RequestMixin, generics.GenericAPIView):
    serializer_class = DecideSerializer

    @extend_schema(responses={200: ApprovalRequestSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        req = services.decide(workspace_object(ApprovalRequest, request, pk=pk), request.user, d["decision"], d.get("comment", ""))
        audit.record(request, "other", req, {"decision": d["decision"], "comment": d.get("comment", "")})
        return self.respond(req)


class ApprovalCancelView(RequestMixin, generics.GenericAPIView):
    serializer_class = ApprovalRequestSerializer

    @extend_schema(request=None, responses={200: ApprovalRequestSerializer})
    def post(self, request, workspace, pk):
        req = services.cancel(workspace_object(ApprovalRequest, request, pk=pk), request.user, request.membership.has_perm("approvals.manage"))
        return self.respond(req)


class ApprovalStatusView(RequestMixin, generics.GenericAPIView):
    """The approval state of one document, for its page."""

    serializer_class = ApprovalStatusSerializer

    @extend_schema(parameters=[OpenApiParameter("document_type", OpenApiTypes.STR, required=True, enum=list(DOCS)),
                               OpenApiParameter("object_id", OpenApiTypes.UUID, required=True)])
    def get(self, request, workspace):
        doc_type = request.query_params.get("document_type")
        if doc_type not in DOCS:
            raise ValidationError({"document_type": ["Unknown document type."]})
        try:
            obj = DOCS[doc_type].get(request.workspace, request.query_params.get("object_id"))
        except Exception as exc:  # noqa: BLE001 - a malformed id
            raise NotFound("Document not found.") from exc
        if obj is None:
            raise NotFound("Document not found.")
        data = services.status_for(request.workspace, doc_type, obj, request.user, request.membership)
        return Response(ApprovalStatusSerializer(data, context=self.get_serializer_context()).data)
