from django.urls import path

from . import views

urlpatterns = [
    path("", views.ReceiptListCreateView.as_view(), name="receipt-list"),
    path("<uuid:pk>/", views.ReceiptDetailView.as_view(), name="receipt-detail"),
    path("<uuid:pk>/void/", views.ReceiptVoidView.as_view(), name="receipt-void"),
]
