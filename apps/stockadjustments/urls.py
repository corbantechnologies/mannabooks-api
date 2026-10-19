from django.urls import path

from . import views

urlpatterns = [
    path("", views.StockAdjustmentListCreateView.as_view(), name="stock-adjustment-list"),
    path("<uuid:pk>/", views.StockAdjustmentDetailView.as_view(), name="stock-adjustment-detail"),
    path("<uuid:pk>/void/", views.StockAdjustmentVoidView.as_view(), name="stock-adjustment-void"),
]
