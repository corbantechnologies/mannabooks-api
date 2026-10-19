from django.urls import path

from . import views

urlpatterns = [
    path("", views.BankTransferListCreateView.as_view(), name="bank-transfer-list"),
    path("<uuid:pk>/void/", views.BankTransferVoidView.as_view(), name="bank-transfer-void"),
]
