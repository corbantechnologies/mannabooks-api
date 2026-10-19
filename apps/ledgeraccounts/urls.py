from django.urls import path

from . import views

urlpatterns = [
    path("", views.LedgerAccountListCreateView.as_view(), name="ledgeraccount-list"),
    path("<uuid:pk>/", views.LedgerAccountDetailView.as_view(), name="ledgeraccount-detail"),
    path("<uuid:pk>/ledger/", views.AccountLedgerView.as_view(), name="ledgeraccount-ledger"),
]
