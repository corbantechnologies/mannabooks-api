from django.urls import path

from . import views

urlpatterns = [
    path("", views.AuditLogListView.as_view(), name="auditlog-list"),
]
