from django.urls import path

from . import views

urlpatterns = [
    path("", views.SupplierPaymentListCreateView.as_view(), name="supplier-payment-list"),
    path("<uuid:pk>/", views.SupplierPaymentDetailView.as_view(), name="supplier-payment-detail"),
    path("<uuid:pk>/void/", views.SupplierPaymentVoidView.as_view(), name="supplier-payment-void"),
]
