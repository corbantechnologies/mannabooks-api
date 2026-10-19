from django.urls import path

from . import views

urlpatterns = [
    path("", views.PayRunListCreateView.as_view(), name="pay-run-list"),
    path("<uuid:pk>/", views.PayRunDetailView.as_view(), name="pay-run-detail"),
    path("<uuid:pk>/action/", views.PayRunActionView.as_view(), name="pay-run-action"),
]
