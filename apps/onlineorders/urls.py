from django.urls import path

from . import views

urlpatterns = [
    path("", views.OrderListView.as_view(), name="online-order-list"),
    path("<uuid:pk>/", views.OrderDetailView.as_view(), name="online-order-detail"),
    path("<uuid:pk>/action/", views.OrderActionView.as_view(), name="online-order-action"),
]
