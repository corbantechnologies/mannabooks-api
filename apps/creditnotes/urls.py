from django.urls import path

from . import views

urlpatterns = [
    path("", views.CreditNoteListCreateView.as_view(), name="creditnote-list"),
    path("<uuid:pk>/", views.CreditNoteDetailView.as_view(), name="creditnote-detail"),
    path("<uuid:pk>/void/", views.CreditNoteVoidView.as_view(), name="creditnote-void"),
]
