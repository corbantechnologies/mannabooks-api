from django.urls import path

from . import views

urlpatterns = [
    path("", views.InboxListView.as_view(), name="inbox-list"),
    path("sent/", views.SentListView.as_view(), name="inbox-sent"),
    path("preview/", views.PreviewView.as_view(), name="inbox-preview"),
    path("send/", views.SendView.as_view(), name="inbox-send"),
    path("<uuid:pk>/", views.InboxDetailView.as_view(), name="inbox-detail"),
    path("<uuid:pk>/accept/", views.AcceptView.as_view(), name="inbox-accept"),
    path("<uuid:pk>/decline/", views.DeclineView.as_view(), name="inbox-decline"),
]
