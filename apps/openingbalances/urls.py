from django.urls import path

from . import views

urlpatterns = [
    path("", views.OpeningBalanceView.as_view(), name="openingbalance"),
    path("post/", views.OpeningBalancePostView.as_view(), name="openingbalance-post"),
    path("unpost/", views.OpeningBalanceUnpostView.as_view(), name="openingbalance-unpost"),
]
