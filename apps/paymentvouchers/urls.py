from django.urls import path

from . import views

urlpatterns = [
    path("", views.PaymentVoucherListCreateView.as_view(), name="payment-voucher-list"),
    path("<uuid:pk>/", views.PaymentVoucherDetailView.as_view(), name="payment-voucher-detail"),
    path("<uuid:pk>/action/", views.PaymentVoucherActionView.as_view(), name="payment-voucher-action"),
]
