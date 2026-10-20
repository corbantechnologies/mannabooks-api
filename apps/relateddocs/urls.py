from django.urls import path

from . import views

urlpatterns = [path("", views.RelatedDocumentsView.as_view(), name="related-documents")]
