from django.urls import path

from . import views

urlpatterns = [
    path("", views.SupplierListCreateView.as_view(), name="supplier-list"),
    path("<uuid:pk>/", views.SupplierDetailView.as_view(), name="supplier-detail"),
    path("<uuid:pk>/statement/", views.SupplierStatementView.as_view(), name="supplier-statement"),
]
