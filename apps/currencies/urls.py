from django.urls import path

from . import views

urlpatterns = [
    path("", views.CurrencyListCreateView.as_view(), name="currency-list"),
    path("<uuid:pk>/", views.CurrencyDetailView.as_view(), name="currency-detail"),
]
