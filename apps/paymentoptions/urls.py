from django.urls import path

from . import views

urlpatterns = [
    path("", views.PaymentOptionListCreateView.as_view(), name="payment-option-list"),
    path("<uuid:pk>/", views.PaymentOptionDetailView.as_view(), name="payment-option-detail"),
]
