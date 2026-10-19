from django.urls import path

from . import views

urlpatterns = [
    path("", views.OtherIncomeListCreateView.as_view(), name="other-income-list"),
    path("<uuid:pk>/", views.OtherIncomeDetailView.as_view(), name="other-income-detail"),
    path("<uuid:pk>/void/", views.OtherIncomeVoidView.as_view(), name="other-income-void"),
]
