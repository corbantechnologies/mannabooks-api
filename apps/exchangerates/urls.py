from django.urls import path

from . import views

urlpatterns = [
    path("", views.ExchangeRateListCreateView.as_view(), name="exchangerate-list"),
    path("<uuid:pk>/", views.ExchangeRateDetailView.as_view(), name="exchangerate-detail"),
]
