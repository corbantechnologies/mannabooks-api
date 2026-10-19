from django.urls import path

from . import views

urlpatterns = [
    path("", views.DepreciationRunsView.as_view(), name="depreciation-runs"),
    path("preview/", views.DepreciationPreviewView.as_view(), name="depreciation-preview"),
    path("run/", views.DepreciationRunView.as_view(), name="depreciation-run"),
    path("undo/", views.DepreciationUndoView.as_view(), name="depreciation-undo"),
]
