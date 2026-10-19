from django.urls import path

from . import views

urlpatterns = [
    path("", views.InvoiceListCreateView.as_view(), name="invoice-list"),
    path("<uuid:pk>/", views.InvoiceDetailView.as_view(), name="invoice-detail"),
    path("<uuid:pk>/issue/", views.InvoiceIssueView.as_view(), name="invoice-issue"),
    path("<uuid:pk>/void/", views.InvoiceVoidView.as_view(), name="invoice-void"),
]
