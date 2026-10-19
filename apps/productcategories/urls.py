from django.urls import path

from . import views

urlpatterns = [
    path("", views.ProductCategoryListCreateView.as_view(), name="product-category-list"),
    path("<uuid:pk>/", views.ProductCategoryDetailView.as_view(), name="product-category-detail"),
]
