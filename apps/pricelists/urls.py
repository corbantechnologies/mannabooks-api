from django.urls import path

from . import views

urlpatterns = [
    path("", views.PriceListListCreateView.as_view(), name="price-list-list"),
    path("customer-prices/", views.CustomerPricesView.as_view(), name="customer-prices"),
    path("<uuid:pk>/", views.PriceListDetailView.as_view(), name="price-list-detail"),
]
