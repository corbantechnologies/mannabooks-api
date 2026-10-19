from django.urls import path

from . import views

urlpatterns = [
    path("", views.PortalLinkListCreateView.as_view(), name="portal-link-list"),
    path("<uuid:pk>/", views.PortalLinkDetailView.as_view(), name="portal-link-detail"),
]
