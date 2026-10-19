from django.db.models import Q
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.employees.models import Employee
from apps.reportrequests.models import ReportRequest

from . import services
from .models import ReportSubmission
from .serializers import (
    PersonSerializer,
    ReportRequestSerializer,
    ReportSubmissionSerializer,
    ReportSubmitSerializer,
    RequestUpdateSerializer,
    ReviewSerializer,
)


def _download(field, name):
    if not field:
        raise NotFound("No file.")
    return FileResponse(field.open("rb"), as_attachment=True, filename=name or field.name.rsplit("/", 1)[-1])


class RequestMixin(WorkspaceScopedMixin):
    """Anyone may see the requests they made; workreports.view sees all."""

    permission_map = {"GET": None, "POST": "workreports.request", "PATCH": "workreports.request", "DELETE": "workreports.request"}
    queryset = ReportRequest.objects.select_related("department", "created_by").prefetch_related("assignees", "submissions")
    serializer_class = ReportRequestSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def workspace_queryset(self):
        qs = super().workspace_queryset()
        if self.request.membership.has_perm("workreports.view"):
            return qs
        return qs.filter(created_by=self.request.user)


class ReportRequestListCreateView(RequestMixin, generics.ListCreateAPIView):
    filterset_fields = ["status", "frequency"]
    search_fields = ["title"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = dict(serializer.validated_data)
        template = d.pop("template_file", None)
        ids = d.pop("people_ids", [])
        people = list(Employee.objects.filter(workspace=request.workspace, pk__in=ids))
        req = services.create(request.workspace, user=request.user, membership=request.membership, data=d, template=template, people=people)
        audit.record(request, "create", req)
        return Response(ReportRequestSerializer(self.get_queryset().get(pk=req.pk), context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED)


class ReportRequestDetailView(RequestMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return RequestUpdateSerializer if self.request.method == "PATCH" else ReportRequestSerializer

    def check_owner(self, req):
        if req.created_by_id != self.request.user.id and not self.request.membership.has_perm("workreports.manage"):
            raise PermissionDenied("Only the person who made this request can change it.")

    def perform_update(self, serializer):
        self.check_owner(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self.check_owner(instance)
        if instance.submissions.exclude(status__in=["pending", "late"]).exists():
            raise BusinessRuleError("Reports have come in for this request. Close it instead.")
        super().perform_destroy(instance)


class ReportTemplateView(RequestMixin, generics.GenericAPIView):
    """Download the request's template. Anyone asked, or the requester."""

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    def get(self, request, workspace, pk):
        req = workspace_object(ReportRequest, request, pk=pk)
        allowed = (req.created_by_id == request.user.id or request.membership.has_perm("workreports.view")
                   or req.assignees.filter(membership__user=request.user).exists())
        if not allowed:
            raise NotFound("Not found.")
        return _download(req.template, req.template_name)


class AskablePeopleView(WorkspaceScopedMixin, generics.GenericAPIView):
    """The people the caller may ask for reports."""

    permission_map = {"GET": "workreports.request"}
    queryset = Employee.objects.all()
    serializer_class = PersonSerializer
    pagination_class = None

    @extend_schema(responses={200: PersonSerializer(many=True)})
    def get(self, request, workspace):
        people = services.askable(request.workspace, request.user, request.membership)
        return Response(PersonSerializer(sorted(people, key=lambda e: e.full_name), many=True).data)


class SubmissionMixin(WorkspaceScopedMixin):
    permission_map = {"GET": None, "POST": None}
    queryset = ReportSubmission.objects.select_related("request__created_by", "employee__membership", "reviewed_by")
    serializer_class = ReportSubmissionSerializer

    def workspace_queryset(self):
        qs = super().workspace_queryset()
        if self.request.membership.has_perm("workreports.view"):
            return qs
        u = self.request.user
        return qs.filter(Q(employee__membership__user=u) | Q(request__created_by=u))


class ReportSubmissionListView(SubmissionMixin, generics.ListAPIView):
    """`?box=todo` (mine to write), `review` (reports for my requests), or `all`."""

    filterset_fields = ["status", "request", "employee"]
    search_fields = ["request__title", "employee__first_name", "employee__last_name"]

    @extend_schema(parameters=[OpenApiParameter("box", OpenApiTypes.STR, enum=["todo", "review", "all"])])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def workspace_queryset(self):
        qs = super().workspace_queryset()
        box = self.request.query_params.get("box", "todo")
        if box == "todo":
            return qs.filter(employee__membership__user=self.request.user)
        if box == "review":
            return qs.filter(request__created_by=self.request.user)
        return qs


class ReportSubmissionDetailView(SubmissionMixin, generics.RetrieveAPIView):
    pass


class ReportSubmitView(SubmissionMixin, generics.GenericAPIView):
    serializer_class = ReportSubmitSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(responses={200: ReportSubmissionSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sub = services.submit(self.get_object(), user=request.user, body=serializer.validated_data.get("body", ""),
                              upload=serializer.validated_data.get("file"))
        return Response(ReportSubmissionSerializer(self.queryset.get(pk=sub.pk), context=self.get_serializer_context()).data)

    def get_object(self):
        return workspace_object(self.get_queryset(), self.request, pk=self.kwargs["pk"])


class ReportReviewView(SubmissionMixin, generics.GenericAPIView):
    serializer_class = ReviewSerializer

    @extend_schema(responses={200: ReportSubmissionSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        sub = services.review(workspace_object(self.get_queryset(), request, pk=pk), user=request.user, membership=request.membership,
                              decision=d["decision"], comment=d.get("comment", ""))
        audit.record(request, "other", sub, {"review": d["decision"]})
        return Response(ReportSubmissionSerializer(self.queryset.get(pk=sub.pk), context=self.get_serializer_context()).data)


class ReportFileView(SubmissionMixin, generics.GenericAPIView):
    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: OpenApiResponse(description="No file")})
    def get(self, request, workspace, pk):
        sub = workspace_object(self.get_queryset(), request, pk=pk)
        return _download(sub.file, sub.file_name)
