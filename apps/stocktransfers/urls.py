from django.urls import path

from . import views

urlpatterns = [
    path("", views.StockTransferListCreateView.as_view(), name="stock-transfer-list"),
    path("<uuid:pk>/", views.StockTransferDetailView.as_view(), name="stock-transfer-detail"),
    path("<uuid:pk>/void/", views.StockTransferVoidView.as_view(), name="stock-transfer-void"),
]
