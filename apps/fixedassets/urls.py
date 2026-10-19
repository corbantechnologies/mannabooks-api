from django.urls import path

from . import views

urlpatterns = [
    path("", views.FixedAssetListCreateView.as_view(), name="fixed-asset-list"),
    path("categories/", views.CategoryDefaultsView.as_view(), name="fixed-asset-categories"),
    path("<uuid:pk>/", views.FixedAssetDetailView.as_view(), name="fixed-asset-detail"),
    path("<uuid:pk>/action/", views.FixedAssetActionView.as_view(), name="fixed-asset-action"),
    path("<uuid:pk>/schedule/", views.FixedAssetScheduleView.as_view(), name="fixed-asset-schedule"),
]
