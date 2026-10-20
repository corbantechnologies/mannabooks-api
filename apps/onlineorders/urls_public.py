from django.urls import path

from . import views

urlpatterns = [
    path("<slug:slug>/", views.ShopView.as_view(), name="shop"),
    path("<slug:slug>/orders/", views.PlaceOrderView.as_view(), name="shop-place-order"),
    path("<slug:slug>/orders/<str:token>/", views.PublicOrderView.as_view(), name="shop-order"),
    path("<slug:slug>/orders/<str:token>/pay/", views.PublicPayView.as_view(), name="shop-order-pay"),
]
