from django.urls import path

from . import views

urlpatterns = [
    path("", views.ActivityListCreateView.as_view(), name="activity-list"),
    path("<uuid:pk>/", views.ActivityDetailView.as_view(), name="activity-detail"),
]
