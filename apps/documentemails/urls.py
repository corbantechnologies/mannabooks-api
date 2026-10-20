from django.urls import path

from . import views

urlpatterns = [
    path("", views.DocumentEmailListCreateView.as_view(), name="document-email-list"),
    path("draft/", views.DocumentEmailDraftView.as_view(), name="document-email-draft"),
    path("pdf/", views.DocumentPdfView.as_view(), name="document-pdf"),
]
