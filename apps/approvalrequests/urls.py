from django.urls import path

from . import views

urlpatterns = [
    path("", views.ApprovalRequestListCreateView.as_view(), name="approval-request-list"),
    path("status/", views.ApprovalStatusView.as_view(), name="approval-status"),
    path("<uuid:pk>/", views.ApprovalRequestDetailView.as_view(), name="approval-request-detail"),
    path("<uuid:pk>/decide/", views.ApprovalDecideView.as_view(), name="approval-decide"),
    path("<uuid:pk>/cancel/", views.ApprovalCancelView.as_view(), name="approval-cancel"),
]
