from django.urls import path

from . import views

urlpatterns = [
    path("", views.RecurringListCreateView.as_view(), name="recurring-invoice-list"),
    path("<uuid:pk>/", views.RecurringDetailView.as_view(), name="recurring-invoice-detail"),
    path("<uuid:pk>/action/", views.RecurringActionView.as_view(), name="recurring-invoice-action"),
]
