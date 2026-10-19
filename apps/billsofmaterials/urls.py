from django.urls import path

from . import views

urlpatterns = [
    path("", views.BillOfMaterialsListCreateView.as_view(), name="bom-list"),
    path("<uuid:pk>/", views.BillOfMaterialsDetailView.as_view(), name="bom-detail"),
]
