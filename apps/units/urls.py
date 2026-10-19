from django.urls import path

from . import views

urlpatterns = [
    path("", views.UnitListCreateView.as_view(), name="unit-list"),
    path("<uuid:pk>/", views.UnitDetailView.as_view(), name="unit-detail"),
]
