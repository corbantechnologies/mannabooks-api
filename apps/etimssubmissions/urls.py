from django.urls import path

from . import views

urlpatterns = [
    path("", views.EtimsSubmissionListView.as_view(), name="etims-submission-list"),
]
