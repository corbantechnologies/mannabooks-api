from django.urls import path

from . import views

urlpatterns = [
    path("", views.SequenceListView.as_view(), name="sequence-list"),
    path("<uuid:pk>/", views.SequenceDetailView.as_view(), name="sequence-detail"),
]
