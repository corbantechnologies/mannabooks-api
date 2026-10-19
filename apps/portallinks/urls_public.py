from django.urls import path

from . import views

urlpatterns = [
    path("<str:token>/", views.PublicPortalView.as_view(), name="portal"),
    path("<str:token>/pay/", views.PublicPortalPayView.as_view(), name="portal-pay"),
    path("<str:token>/pay/<uuid:pk>/", views.PublicPortalPaymentStatusView.as_view(), name="portal-pay-status"),
]
