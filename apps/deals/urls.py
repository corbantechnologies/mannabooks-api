from django.urls import path

from . import views

urlpatterns = [
    path("", views.DealListCreateView.as_view(), name="deal-list"),
    path("pipeline/", views.PipelineView.as_view(), name="deal-pipeline"),
    path("<uuid:pk>/", views.DealDetailView.as_view(), name="deal-detail"),
    path("<uuid:pk>/move/", views.DealMoveView.as_view(), name="deal-move"),
]
