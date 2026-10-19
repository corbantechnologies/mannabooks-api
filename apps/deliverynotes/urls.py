from django.urls import path

from . import views

urlpatterns = [
    path("", views.DeliveryNoteListCreateView.as_view(), name="delivery-note-list"),
    path("<uuid:pk>/", views.DeliveryNoteDetailView.as_view(), name="delivery-note-detail"),
    path("<uuid:pk>/status/", views.DeliveryNoteStatusView.as_view(), name="delivery-note-status"),
]
