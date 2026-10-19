from django.urls import path

from . import views

urlpatterns = [
    path("rules/", views.ReminderRuleListCreateView.as_view(), name="reminder-rule-list"),
    path("rules/<uuid:pk>/", views.ReminderRuleDetailView.as_view(), name="reminder-rule-detail"),
    path("sent/", views.ReminderLogListView.as_view(), name="reminder-log-list"),
    path("send/", views.SendReminderView.as_view(), name="reminder-send"),
]
