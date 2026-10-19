from django.urls import path

from . import views

urlpatterns = [
    path("", views.ReportRequestListCreateView.as_view(), name="report-request-list"),
    path("people/", views.AskablePeopleView.as_view(), name="report-request-people"),
    path("<uuid:pk>/", views.ReportRequestDetailView.as_view(), name="report-request-detail"),
    path("<uuid:pk>/template/", views.ReportTemplateView.as_view(), name="report-request-template"),
]
