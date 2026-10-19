from django.urls import path

from . import views

urlpatterns = [
    path("", views.TaxRateListCreateView.as_view(), name="taxrate-list"),
    path("<uuid:pk>/", views.TaxRateDetailView.as_view(), name="taxrate-detail"),
]
