"""Routes for the workspace itself, mounted at /api/v1/w/<workspace>/."""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.WorkspaceDetailView.as_view(), name="workspace-detail"),
    path("context/", views.WorkspaceContextView.as_view(), name="workspace-context"),
]
