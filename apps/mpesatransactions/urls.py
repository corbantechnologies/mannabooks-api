from django.urls import path

from . import views

urlpatterns = [
    path("", views.MpesaTransactionListView.as_view(), name="mpesa-transaction-list"),
    path("prompt/", views.PaymentPromptView.as_view(), name="mpesa-prompt"),
    path("<uuid:pk>/", views.MpesaTransactionDetailView.as_view(), name="mpesa-transaction-detail"),
    path("<uuid:pk>/apply/", views.ApplyMpesaView.as_view(), name="mpesa-transaction-apply"),
]
