from django.urls import path

from . import views

urlpatterns = [
    path("", views.CostCenterListCreateView.as_view(), name="cost-center-list"),
    path("<uuid:pk>/", views.CostCenterDetailView.as_view(), name="cost-center-detail"),
]
