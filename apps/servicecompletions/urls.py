from django.urls import path

from . import views

urlpatterns = [
    path("", views.ServiceCompletionListCreateView.as_view(), name="service-completion-list"),
    path("<uuid:pk>/", views.ServiceCompletionDetailView.as_view(), name="service-completion-detail"),
]
