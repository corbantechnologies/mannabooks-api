from django.urls import path

from . import views

urlpatterns = [
    path("", views.StockTakeListCreateView.as_view(), name="stock-take-list"),
    path("<uuid:pk>/", views.StockTakeDetailView.as_view(), name="stock-take-detail"),
    path("<uuid:pk>/counts/", views.StockTakeCountsView.as_view(), name="stock-take-counts"),
    path("<uuid:pk>/action/", views.StockTakeActionView.as_view(), name="stock-take-action"),
]
