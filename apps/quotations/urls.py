from django.urls import path

from . import views

urlpatterns = [
    path("", views.QuotationListCreateView.as_view(), name="quotation-list"),
    path("<uuid:pk>/", views.QuotationDetailView.as_view(), name="quotation-detail"),
    path("<uuid:pk>/status/", views.QuotationActionView.as_view(), name="quotation-status"),
    path("<uuid:pk>/convert/", views.QuotationConvertView.as_view(), name="quotation-convert"),
]
