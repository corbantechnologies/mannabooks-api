from django.urls import path

from . import views

urlpatterns = [
    path("", views.ExpenseListCreateView.as_view(), name="expense-list"),
    path("<uuid:pk>/", views.ExpenseDetailView.as_view(), name="expense-detail"),
    path("<uuid:pk>/void/", views.ExpenseVoidView.as_view(), name="expense-void"),
]
