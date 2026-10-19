from django.urls import path

from . import views

urlpatterns = [
    path("", views.ReportSubmissionListView.as_view(), name="report-submission-list"),
    path("<uuid:pk>/", views.ReportSubmissionDetailView.as_view(), name="report-submission-detail"),
    path("<uuid:pk>/submit/", views.ReportSubmitView.as_view(), name="report-submission-submit"),
    path("<uuid:pk>/review/", views.ReportReviewView.as_view(), name="report-submission-review"),
    path("<uuid:pk>/file/", views.ReportFileView.as_view(), name="report-submission-file"),
]
