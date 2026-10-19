from django.urls import path

from . import views

urlpatterns = [
    path("", views.RoleListCreateView.as_view(), name="role-list"),
    path("permissions/", views.PermissionCatalogView.as_view(), name="role-permissions"),
    path("<uuid:pk>/", views.RoleDetailView.as_view(), name="role-detail"),
]
