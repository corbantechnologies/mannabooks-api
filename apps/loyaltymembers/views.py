from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.loyaltyprograms.models import LoyaltyProgram
from apps.sequences.services import next_value

from .models import LoyaltyMember
from .serializers import AdjustPointsSerializer, LoyaltyMemberSerializer


class MemberMixin(WorkspaceScopedMixin):
    permission_map = {"GET": "loyalty.view", "POST": "loyalty.enrol", "PATCH": "loyalty.manage"}
    queryset = LoyaltyMember.objects.select_related("customer", "tier")
    serializer_class = LoyaltyMemberSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self.request, "workspace", None):
            ctx["program"] = LoyaltyProgram.objects.filter(workspace=self.request.workspace).first()
        return ctx


class LoyaltyMemberListCreateView(MemberMixin, generics.ListCreateAPIView):
    """Members. `?lookup=` finds one by card number or phone (for the till)."""

    filterset_fields = ["tier", "is_active", "customer"]
    search_fields = ["card_number", "customer__name", "customer__phone"]
    ordering_fields = ["points_balance", "lifetime_points", "created_at"]

    def workspace_queryset(self):
        qs = super().workspace_queryset()
        lookup = self.request.query_params.get("lookup", "").strip()
        if lookup:
            digits = "".join(c for c in lookup if c.isdigit())[-9:]
            match = Q(card_number__iexact=lookup)
            if len(digits) == 9:
                match |= Q(customer__phone__endswith=digits)
            qs = qs.filter(match)
        return qs

    def perform_create(self, serializer):
        program = LoyaltyProgram.objects.filter(workspace=self.request.workspace, is_active=True).first()
        if program is None:
            raise BusinessRuleError("Switch the loyalty programme on first (Sales > Loyalty > Settings).")
        card = serializer.validated_data.get("card_number") or next_value(self.request.workspace, "loyalty_member")
        member = serializer.save(workspace=self.request.workspace, created_by=self.request.user, card_number=card)
        audit.record(self.request, "create", member)


class LoyaltyMemberDetailView(MemberMixin, generics.RetrieveUpdateAPIView):
    http_method_names = ["get", "patch"]


class AdjustPointsView(MemberMixin, generics.GenericAPIView):
    permission_map = {"POST": "loyalty.manage"}
    serializer_class = AdjustPointsSerializer

    @extend_schema(responses={200: LoyaltyMemberSerializer})
    def post(self, request, workspace, pk):
        from apps.loyaltytransactions.services import adjust

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = workspace_object(LoyaltyMember, request, pk=pk)
        adjust(member, serializer.validated_data["points"], serializer.validated_data["reason"], request.user)
        audit.record(request, "other", member, serializer.validated_data)
        member.refresh_from_db()
        return Response(LoyaltyMemberSerializer(member, context=self.get_serializer_context()).data)
