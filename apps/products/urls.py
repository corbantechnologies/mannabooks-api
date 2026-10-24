from django.urls import path

from . import views

urlpatterns = [
    path("", views.ProductListCreateView.as_view(), name="product-list"),
    path("bulk/", views.ProductBulkCreateView.as_view(), name="product-bulk"),
    path("<uuid:pk>/", views.ProductDetailView.as_view(), name="product-detail"),
]
