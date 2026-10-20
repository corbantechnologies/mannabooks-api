from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import OnlineOrder
from .serializers import (
    OnlineOrderActionSerializer,
    OnlineOrderSerializer,
    PayOrderSerializer,
    PlaceOrderSerializer,
    PublicOrderSerializer,
    ShopSerializer,
)


# ---------------------------------------------------------------- the public shop (no sign-in)
class PublicMixin:
    permission_classes = [AllowAny]
    authentication_classes = []


class ShopView(PublicMixin, APIView):
    @extend_schema(responses={200: ShopSerializer})
    def get(self, request, slug):
        ws = services.open_store(slug)
        data = {
            "name": ws.name, "intro": ws.store_intro, "phone": ws.phone, "email": ws.email, "address": ws.address, "logo_url": ws.logo_url,
            "currency": ws.currency, "allow_pickup": ws.store_allow_pickup, "allow_delivery": ws.store_allow_delivery,
            "delivery_fee": ws.store_delivery_fee, "pay_on_delivery": ws.store_pay_on_delivery, "mpesa": services.mpesa_ready(ws),
            "products": services.catalogue(ws),
        }
        return Response(ShopSerializer(data).data)


class PlaceOrderView(PublicMixin, APIView):
    """Place an order. Paying by M-Pesa sends the prompt straight away; if that fails the order still stands and can be paid later."""

    @extend_schema(request=PlaceOrderSerializer, responses={201: PublicOrderSerializer})
    def post(self, request, slug):
        ws = services.open_store(slug)
        serializer = PlaceOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        order = services.place(ws, customer_name=d["customer_name"], phone=d["phone"], email=d.get("email", ""), fulfilment=d["fulfilment"],
                               address=d.get("address", ""), notes=d.get("notes", ""), payment_method=d["payment_method"], rows=d["lines"])
        data = PublicOrderSerializer(order).data
        if order.payment_method == OnlineOrder.PaymentMethod.MPESA:
            try:
                services.request_payment(order)
                data = PublicOrderSerializer(order).data
            except BusinessRuleError as exc:
                data["payment_error"] = str(exc)
        return Response(data, status=status.HTTP_201_CREATED)


class PublicOrderView(PublicMixin, APIView):
    @extend_schema(responses={200: PublicOrderSerializer})
    def get(self, request, slug, token):
        ws = services.open_store(slug)
        return Response(PublicOrderSerializer(get_object_or_404(OnlineOrder, workspace=ws, token=token)).data)


class PublicPayView(PublicMixin, APIView):
    @extend_schema(request=PayOrderSerializer, responses={200: PublicOrderSerializer})
    def post(self, request, slug, token):
        ws = services.open_store(slug)
        order = get_object_or_404(OnlineOrder, workspace=ws, token=token)
        serializer = PayOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(PublicOrderSerializer(services.request_payment(order, serializer.validated_data.get("phone") or None)).data)


# ---------------------------------------------------------------- the shop's side
class OrderMixin(WorkspaceScopedMixin):
    module = "onlineorders"
    queryset = OnlineOrder.objects.select_related("mpesa_transaction", "receipt")
    serializer_class = OnlineOrderSerializer


class OrderListView(OrderMixin, generics.ListAPIView):
    filterset_fields = ["status", "fulfilment", "payment_method"]
    search_fields = ["number", "customer_name", "phone"]


class OrderDetailView(OrderMixin, generics.RetrieveAPIView):
    pass


class OrderActionView(OrderMixin, generics.GenericAPIView):
    permission_map = {"POST": "onlineorders.manage"}
    serializer_class = OnlineOrderActionSerializer

    @extend_schema(responses={200: OnlineOrderSerializer})
    def post(self, request, workspace, pk):
        order = workspace_object(OnlineOrder, request, pk=pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        action = d["action"]
        if action in services.STEPS:
            services.advance(order, action)
        elif action == "cancel":
            services.cancel(order, d.get("reason", ""))
        elif action == "request_payment":
            services.request_payment(order)
        else:
            if not request.membership.has_perm("receipts.create"):
                raise BusinessRuleError("Completing an order records a cash sale, which your role can't do.")
            services.complete(order, method=d.get("method", ""), payment_reference=d.get("payment_reference", ""),
                              deposit_account=d.get("deposit_account"), user=request.user)
        order.refresh_from_db()
        audit.record(request, "other", order, {"action": action, "status": order.status})
        return Response(OnlineOrderSerializer(order).data)
