from django.urls import path

from . import views

urlpatterns = [path("", views.LoyaltyTransactionListView.as_view(), name="loyalty-transaction-list")]
