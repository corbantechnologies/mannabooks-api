from django.urls import path

from . import views

urlpatterns = [
    path("", views.LeadListCreateView.as_view(), name="lead-list"),
    path("<uuid:pk>/", views.LeadDetailView.as_view(), name="lead-detail"),
    path("<uuid:pk>/action/", views.LeadActionView.as_view(), name="lead-action"),
]
