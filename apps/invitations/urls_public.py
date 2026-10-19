"""Invitation links, mounted at /api/v1/invitations/ (not inside a workspace)."""
from django.urls import path

from . import views

urlpatterns = [
    path("<str:token>/", views.InvitationPreviewView.as_view(), name="invitation-preview"),
    path("<str:token>/accept/", views.InvitationAcceptView.as_view(), name="invitation-accept"),
]
