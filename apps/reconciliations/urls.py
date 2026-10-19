from django.urls import path

from . import views

urlpatterns = [
    path("", views.ReconciliationListCreateView.as_view(), name="reconciliation-list"),
    path("<uuid:pk>/", views.ReconciliationDetailView.as_view(), name="reconciliation-detail"),
    path("<uuid:pk>/lines/", views.ReconciliationLinesView.as_view(), name="reconciliation-lines"),
    path("<uuid:pk>/action/", views.ReconciliationActionView.as_view(), name="reconciliation-action"),
]
