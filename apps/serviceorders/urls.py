from django.urls import path

from . import views

urlpatterns = [
    path("", views.ServiceOrderListCreateView.as_view(), name="service-order-list"),
    path("<uuid:pk>/", views.ServiceOrderDetailView.as_view(), name="service-order-detail"),
    path("<uuid:pk>/action/", views.ServiceOrderActionView.as_view(), name="service-order-action"),
]
