from django.urls import path

from . import views

urlpatterns = [
    path("", views.StatutoryRateListCreateView.as_view(), name="statutory-rate-list"),
    path("<uuid:pk>/", views.StatutoryRateDetailView.as_view(), name="statutory-rate-detail"),
]
