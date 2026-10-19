from django.urls import path

from . import views

urlpatterns = [
    path("", views.LeaveRequestListCreateView.as_view(), name="leave-request-list"),
    path("balances/", views.LeaveBalanceView.as_view(), name="leave-balances"),
    path("<uuid:pk>/action/", views.LeaveDecisionView.as_view(), name="leave-request-action"),
]
