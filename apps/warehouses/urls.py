from django.urls import path

from . import views

urlpatterns = [
    path("", views.WarehouseListCreateView.as_view(), name="warehouse-list"),
    path("<uuid:pk>/", views.WarehouseDetailView.as_view(), name="warehouse-detail"),
]
