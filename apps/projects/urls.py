from django.urls import path

from . import views

urlpatterns = [
    path("", views.ProjectListCreateView.as_view(), name="project-list"),
    path("<uuid:pk>/", views.ProjectDetailView.as_view(), name="project-detail"),
    path("<uuid:pk>/summary/", views.ProjectSummaryView.as_view(), name="project-summary"),
]
