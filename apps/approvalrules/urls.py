from django.urls import path

from . import views

urlpatterns = [
    path("", views.ApprovalRuleListCreateView.as_view(), name="approval-rule-list"),
    path("<uuid:pk>/", views.ApprovalRuleDetailView.as_view(), name="approval-rule-detail"),
]
