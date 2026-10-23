from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin
from apps.ledgeraccounts.views import parse_date

from . import services
from .kinds import PERMS as MORE_PERMS
from .models import ImportJob

IMPORT_PERM = {"customers": "customers.manage", "suppliers": "suppliers.manage", "products": "products.manage", "opening_balances": "openingbalances.manage",
               **MORE_PERMS}


class ImportJobSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)

    class Meta:
        model = ImportJob
        fields = ["id", "kind", "filename", "status", "total_rows", "imported_rows", "skipped_rows", "errors", "created_by_name", "created_at"]
        read_only_fields = fields


class ImportMixin(WorkspaceScopedMixin):
    permission_map = {"GET": None, "POST": None}  # each kind checks its own permission
    queryset = ImportJob.objects.select_related("created_by")
    serializer_class = ImportJobSerializer

    def check_kind(self, kind):
        if kind not in IMPORT_PERM:
            raise BusinessRuleError(f"Import one of: {', '.join(IMPORT_PERM)}.")
        if not self.request.membership.has_perm(IMPORT_PERM[kind]):
            raise PermissionDenied("Your role can't add these records.")


class ImportListCreateView(ImportMixin, generics.ListCreateAPIView):
    """Past imports; POST a CSV to check it (commit=false) or import it (commit=true). Nothing is saved unless every row is right."""

    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request={"multipart/form-data": inline_serializer("ImportUpload", {
        "kind": serializers.ChoiceField(choices=ImportJob.Kind.choices), "file": serializers.FileField(), "commit": serializers.BooleanField(default=False),
        "as_of": serializers.DateField(required=False, help_text="Opening balances: the date they are at")})}, responses={201: ImportJobSerializer})
    def post(self, request, workspace):
        kind = request.data.get("kind", "")
        self.check_kind(kind)
        upload = request.FILES.get("file")
        if upload is None:
            raise BusinessRuleError("Choose a CSV file.")
        commit = str(request.data.get("commit", "")).lower() in ("true", "1", "yes")
        if commit:
            from apps.subscriptions.services import check_write

            check_write(request.workspace, IMPORT_PERM[kind])
        job = services.run(request, kind, upload, commit=commit, as_of=parse_date(request.data.get("as_of"), "as_of"))
        if job.status == ImportJob.Status.IMPORTED:
            audit.record(request, "create", job, {"rows": job.imported_rows})
        return Response(ImportJobSerializer(job).data, status=status.HTTP_201_CREATED)


class TemplateView(ImportMixin, generics.GenericAPIView):
    """A CSV with the right headings and an example row."""

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.STR})
    def get(self, request, workspace, kind):
        self.check_kind(kind)
        res = HttpResponse(services.template_csv(kind), content_type="text/csv; charset=utf-8")
        res["Content-Disposition"] = f'attachment; filename="mannabooks-{kind}-template.csv"'
        return res


class ExportView(ImportMixin, generics.GenericAPIView):
    """Download a list as CSV: customers, suppliers, products, accounts (with balances), invoices, bills or journal lines."""

    @extend_schema(parameters=[OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE)],
                   responses={(200, "text/csv"): OpenApiTypes.STR})
    def get(self, request, workspace, kind):
        perm = services.EXPORTS.get(kind)
        if perm is None:
            raise BusinessRuleError(f"Export one of: {', '.join(services.EXPORTS)}.")
        if not request.membership.has_perm(perm):
            raise PermissionDenied("Your role can't see these records.")
        data = services.export_csv(request.workspace, kind, from_date=parse_date(request.query_params.get("from"), "from"),
                                   to_date=parse_date(request.query_params.get("to"), "to"))
        res = HttpResponse("﻿" + data, content_type="text/csv; charset=utf-8")  # the BOM lets Excel read accents and KSh correctly
        res["Content-Disposition"] = f'attachment; filename="{request.workspace.slug}-{kind}.csv"'
        return res
