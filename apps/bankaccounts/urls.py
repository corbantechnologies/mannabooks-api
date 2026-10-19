from django.urls import path

from . import views

urlpatterns = [
    path("", views.BankAccountListCreateView.as_view(), name="bank-account-list"),
    path("<uuid:pk>/", views.BankAccountDetailView.as_view(), name="bank-account-detail"),
]
