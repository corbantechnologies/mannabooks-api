from django.urls import path

from . import views

urlpatterns = [
    path("", views.JournalListCreateView.as_view(), name="journal-list"),
    path("<uuid:pk>/", views.JournalDetailView.as_view(), name="journal-detail"),
    path("<uuid:pk>/post/", views.JournalPostView.as_view(), name="journal-post"),
    path("<uuid:pk>/reverse/", views.JournalReverseView.as_view(), name="journal-reverse"),
]
