from django.urls import path

from . import views

urlpatterns = [
    path("", views.InvitationListCreateView.as_view(), name="invitation-list"),
    path("<uuid:pk>/", views.InvitationDetailView.as_view(), name="invitation-detail"),
]
