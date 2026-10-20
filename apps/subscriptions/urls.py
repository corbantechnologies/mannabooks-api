from django.urls import path

from . import views

urlpatterns = [
    path("", views.BillingView.as_view(), name="billing"),
    path("quote/", views.QuoteView.as_view(), name="billing-quote"),
    path("pay/", views.PayView.as_view(), name="billing-pay"),
    path("payments/<uuid:pk>/", views.PaymentStatusView.as_view(), name="billing-payment"),
    path("free/", views.MoveToFreeView.as_view(), name="billing-free"),
]
