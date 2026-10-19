from django.urls import path

from . import views

urlpatterns = [
    path("", views.GoodsReceiptListCreateView.as_view(), name="goods-receipt-list"),
    path("<uuid:pk>/", views.GoodsReceiptDetailView.as_view(), name="goods-receipt-detail"),
    path("<uuid:pk>/void/", views.GoodsReceiptVoidView.as_view(), name="goods-receipt-void"),
]
