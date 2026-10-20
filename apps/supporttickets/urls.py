from django.urls import path

from . import views

urlpatterns = [
    path("", views.TicketListCreateView.as_view(), name="support-list"),
    path("<uuid:pk>/", views.TicketDetailView.as_view(), name="support-detail"),
    path("<uuid:pk>/reply/", views.TicketReplyView.as_view(), name="support-reply"),
    path("<uuid:pk>/close/", views.TicketCloseView.as_view(), name="support-close"),
]
