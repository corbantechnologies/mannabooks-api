from django.urls import path

from . import views

urlpatterns = [
    path("", views.ProductionOrderListCreateView.as_view(), name="production-order-list"),
    path("<uuid:pk>/", views.ProductionOrderDetailView.as_view(), name="production-order-detail"),
    path("<uuid:pk>/action/", views.ProductionOrderActionView.as_view(), name="production-order-action"),
]
