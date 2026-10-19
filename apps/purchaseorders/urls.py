from django.urls import path

from . import views

urlpatterns = [
    path("", views.PurchaseOrderListCreateView.as_view(), name="purchase-order-list"),
    path("<uuid:pk>/", views.PurchaseOrderDetailView.as_view(), name="purchase-order-detail"),
    path("<uuid:pk>/action/", views.PurchaseOrderActionView.as_view(), name="purchase-order-action"),
]
