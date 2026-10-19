from django.urls import path

from . import views

urlpatterns = [
    path("", views.PaymentListCreateView.as_view(), name="payment-list"),
    path("<uuid:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
    path("<uuid:pk>/allocate/", views.PaymentAllocateView.as_view(), name="payment-allocate"),
    path("<uuid:pk>/void/", views.PaymentVoidView.as_view(), name="payment-void"),
]
